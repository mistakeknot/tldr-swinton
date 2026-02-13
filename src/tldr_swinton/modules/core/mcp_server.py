"""
TLDR MCP Server - Model Context Protocol interface for TLDR.

Provides 1:1 mapping with TLDR daemon commands, enabling AI tools
(OpenCode, Claude Desktop, Claude Code) to use TLDR's code analysis.

Usage:
    tldr-mcp --project /path/to/project
"""

import hashlib
import json
import logging
import socket
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP
    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    FastMCP = None
    _MCP_AVAILABLE = False


class _NoMCP:
    def __init__(self, name: str) -> None:
        self.name = name

    def tool(self):
        def decorator(fn):
            return fn
        return decorator

mcp = FastMCP("tldr-code") if _MCP_AVAILABLE else _NoMCP("tldr-code")


def _get_socket_path(project: str) -> Path:
    """Compute socket path matching daemon.py logic."""
    hash_val = hashlib.md5(str(Path(project).resolve()).encode()).hexdigest()[:8]
    return Path(f"/tmp/tldr-{hash_val}.sock")


def _ensure_daemon(project: str, timeout: float = 10.0) -> None:
    """Ensure daemon is running, starting it if needed."""
    socket_path = _get_socket_path(project)

    if socket_path.exists():
        # Try to ping existing daemon
        try:
            result = _send_raw(project, {"cmd": "ping"})
            if result.get("status") == "ok":
                return  # Daemon is alive
        except Exception as e:
            # Socket exists but daemon dead, clean up
            logger.debug(f"Stale socket detected, daemon not responding: {e}")
            socket_path.unlink(missing_ok=True)

    # Start daemon
    subprocess.Popen(
        [sys.executable, "-m", "tldr_swinton.cli", "daemon", "start", "--project", project],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for daemon to be ready
    start = time.time()
    last_error = None
    while time.time() - start < timeout:
        if socket_path.exists():
            try:
                result = _send_raw(project, {"cmd": "ping"})
                if result.get("status") == "ok":
                    return
            except Exception as e:
                last_error = e
        time.sleep(0.1)

    if last_error:
        logger.warning(f"Daemon startup timeout, last error: {last_error}")

    raise RuntimeError(f"Failed to start TLDR daemon for {project}")


def _send_raw(project: str, command: dict) -> dict:
    """Send command to daemon socket."""
    socket_path = _get_socket_path(project)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(socket_path))
        sock.sendall(json.dumps(command).encode() + b"\n")

        # Read response
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            # Check if we have complete JSON
            try:
                return json.loads(b"".join(chunks))
            except json.JSONDecodeError:
                continue

        return json.loads(b"".join(chunks))
    finally:
        sock.close()


def _send_command(project: str, command: dict) -> dict:
    """Send command to daemon, auto-starting if needed."""
    _ensure_daemon(project)
    return _send_raw(project, command)


def _format_context_result(result: dict, fmt: str) -> str:
    if result.get("status") != "ok":
        return str(result)
    ctx = result.get("result", {})
    if isinstance(ctx, str):
        return ctx
    if fmt in ("ultracompact", "json", "json-pretty"):
        from .output_formats import format_context_pack
        return format_context_pack(ctx, fmt=fmt)
    return str(ctx)


# === NAVIGATION TOOLS ===


@mcp.tool()
def tree(project: str = ".", extensions: list[str] | None = None) -> dict:
    """Get file tree structure for a project.

    Args:
        project: Project root directory
        extensions: Optional list of extensions to filter (e.g., [".py", ".ts"])
    """
    return _send_command(
        project,
        {
            "cmd": "tree",
            "extensions": tuple(extensions) if extensions else None,
            "exclude_hidden": True,
        },
    )


@mcp.tool()
def structure(
    project: str = ".", language: str = "python", max_results: int = 100
) -> dict:
    """Get code structure (codemaps) - functions, classes, imports per file.

    Args:
        project: Project root directory
        language: Programming language (python, typescript, go, rust, etc.)
        max_results: Maximum files to analyze
    """
    return _send_command(
        project,
        {"cmd": "structure", "language": language, "max_results": max_results},
    )


@mcp.tool()
def search(project: str, pattern: str, max_results: int = 100) -> dict:
    """Search files for a regex pattern.

    Args:
        project: Project root directory
        pattern: Regex pattern to search for
        max_results: Maximum matches to return
    """
    return _send_command(
        project, {"cmd": "search", "pattern": pattern, "max_results": max_results}
    )


@mcp.tool()
def extract(file: str, compact: bool = False) -> dict:
    """Extract code structure from a file.

    Args:
        file: Path to source file
        compact: If True, return signatures and line numbers only (~87% smaller).
                 Omits call_graph, imports, params, is_async. Bypasses daemon.

    Returns:
        When compact=False: Full structure with imports, functions, classes, call_graph.
        When compact=True: Minimal structure with names, signatures, line numbers only.
    """
    if compact:
        from .api import compact_extract
        return compact_extract(file)
    project = str(Path(file).parent)
    return _send_command(project, {"cmd": "extract", "file": file})


# === CONTEXT TOOLS (Key differentiator - 93%+ token savings) ===


@mcp.tool()
def context(
    project: str,
    entry: str,
    depth: int = 2,
    language: str = "python",
    format: str = "ultracompact",
    budget: int | None = 4000,
    with_docs: bool = False,
    session_id: str | None = None,
    delta: bool = False,
) -> str:
    """Get token-efficient LLM context starting from an entry point.

    Follows call graph to specified depth, returning signatures and complexity
    metrics. Note: The 93% savings figure compares signatures to full files.
    For editing workflows where full code is needed, expect ~20-35% savings.

    Delta mode: Use session_id + delta=True to track unchanged symbols across
    calls. Note: For the `context` tool (signatures-only), delta mode adds
    [UNCHANGED] markers but doesn't reduce output significantly. Use the
    `diff-context` CLI command for ~60% token savings with delta mode.

    Args:
        project: Project root directory
        entry: Entry point (function_name or Class.method)
        depth: How deep to follow calls (default 2)
        language: Programming language
        format: Output format (default: ultracompact for LLMs; also: text, json)
        budget: Token budget (default: 4000; set to None for unlimited)
        with_docs: Include docstrings
        session_id: Session ID for delta caching (auto-generated if delta=True)
        delta: Enable delta mode - unchanged symbols show [UNCHANGED] marker

    Returns:
        LLM-ready formatted context string
    """
    result = _send_command(
        project,
        {
            "cmd": "context",
            "entry": entry,
            "depth": depth,
            "language": language,
            "format": format,
            "budget": budget,
            "with_docs": with_docs,
            "session_id": session_id,
            "delta": delta,
        },
    )
    return _format_context_result(result, format)


# === FLOW ANALYSIS TOOLS ===


@mcp.tool()
def cfg(file: str, function: str, language: str = "python") -> dict:
    """Get control flow graph for a function.

    Returns basic blocks, control flow edges, and cyclomatic complexity.

    Args:
        file: Path to source file
        function: Function name to analyze
        language: Programming language
    """
    project = str(Path(file).parent)
    return _send_command(
        project,
        {"cmd": "cfg", "file": file, "function": function, "language": language},
    )


@mcp.tool()
def dfg(file: str, function: str, language: str = "python") -> dict:
    """Get data flow graph for a function.

    Returns variable references and def-use chains.

    Args:
        file: Path to source file
        function: Function name to analyze
        language: Programming language
    """
    project = str(Path(file).parent)
    return _send_command(
        project,
        {"cmd": "dfg", "file": file, "function": function, "language": language},
    )


@mcp.tool()
def slice(
    file: str,
    function: str,
    line: int,
    direction: str = "backward",
    variable: str | None = None,
    language: str = "python",
) -> dict:
    """Get program slice - lines affecting or affected by a given line.

    Args:
        file: Path to source file
        function: Function name
        line: Line number to slice from
        direction: "backward" (what affects this line) or "forward" (what this line affects)
        variable: Optional specific variable to trace
        language: Programming language

    Returns:
        Dict with lines in the slice and count
    """
    project = str(Path(file).parent)
    return _send_command(
        project,
        {
            "cmd": "slice",
            "file": file,
            "function": function,
            "line": line,
            "direction": direction,
            "variable": variable or "",
            "language": language,
        },
    )


# === CODEBASE ANALYSIS TOOLS ===


@mcp.tool()
def impact(project: str, function: str) -> dict:
    """Find all callers of a function (reverse call graph).

    Useful before refactoring to understand what would break.

    Args:
        project: Project root directory
        function: Function name to find callers of
    """
    return _send_command(project, {"cmd": "impact", "func": function})


@mcp.tool()
def dead(
    project: str,
    entry_points: list[str] | None = None,
    language: str = "python",
) -> dict:
    """Find unreachable (dead) code not called from entry points.

    Args:
        project: Project root directory
        entry_points: List of entry point patterns (default: main, test_, cli)
        language: Programming language
    """
    return _send_command(
        project,
        {"cmd": "dead", "entry_points": entry_points, "language": language},
    )


@mcp.tool()
def arch(project: str, language: str = "python") -> dict:
    """Detect architectural layers from call patterns.

    Identifies entry layer (controllers), middle layer (services),
    and leaf layer (utilities). Also detects circular dependencies.

    Args:
        project: Project root directory
        language: Programming language
    """
    return _send_command(project, {"cmd": "arch", "language": language})


@mcp.tool()
def calls(project: str, language: str = "python") -> dict:
    """Build cross-file call graph for the project.

    Args:
        project: Project root directory
        language: Programming language
    """
    return _send_command(project, {"cmd": "calls", "language": language})


# === IMPORT ANALYSIS ===


@mcp.tool()
def imports(file: str, language: str = "python") -> dict:
    """Parse imports from a source file.

    Args:
        file: Path to source file
        language: Programming language
    """
    project = str(Path(file).parent)
    return _send_command(
        project, {"cmd": "imports", "file": file, "language": language}
    )


@mcp.tool()
def importers(project: str, module: str, language: str = "python") -> dict:
    """Find all files that import a given module.

    Args:
        project: Project root directory
        module: Module name to search for
        language: Programming language
    """
    return _send_command(
        project, {"cmd": "importers", "module": module, "language": language}
    )


# === SEMANTIC SEARCH ===


@mcp.tool()
def semantic(project: str, query: str, k: int = 10) -> dict:
    """Semantic code search using embeddings.

    Searches over function/class summaries using vector similarity.
    Auto-downloads embedding model and builds index on first use.

    Args:
        project: Project root directory
        query: Natural language query
        k: Number of results to return
    """
    return _send_command(
        project, {"cmd": "semantic", "action": "search", "query": query, "k": k}
    )


# === QUALITY TOOLS ===


@mcp.tool()
def diagnostics(path: str, language: str = "python") -> dict:
    """Get type and lint diagnostics.

    For Python: runs pyright (types) + ruff (lint).

    Args:
        path: File or directory path
        language: Programming language
    """
    project = str(Path(path).parent) if Path(path).is_file() else path
    return _send_command(
        project, {"cmd": "diagnostics", "file": path, "language": language}
    )


@mcp.tool()
def change_impact(project: str, files: list[str] | None = None) -> dict:
    """Find tests affected by changed files.

    Uses call graph + import analysis to identify which tests to run.

    Args:
        project: Project root directory
        files: List of changed files (auto-detects from git if None)
    """
    return _send_command(project, {"cmd": "change_impact", "files": files})


# === CONTEXT DELEGATION ===


@mcp.tool()
def delegate(
    project: str,
    task: str,
    current_context: list[str] | None = None,
    budget: int = 8000,
    focus: list[str] | None = None,
) -> str:
    """Get an incremental context retrieval plan instead of raw context.

    Instead of fetching all context upfront, returns a plan that the agent
    can execute step-by-step, reducing wasted retrieval by 50%+.

    Args:
        project: Project root directory
        task: Description of what you're trying to accomplish
        current_context: Symbols you already have (to avoid re-retrieval)
        budget: Maximum tokens to use for context
        focus: Optional specific files/modules to focus on

    Returns:
        Formatted retrieval plan with ordered steps
    """
    from .context_delegation import ContextDelegator, create_delegation_plan

    delegator = ContextDelegator(Path(project))
    plan = delegator.create_plan(
        task_description=task,
        current_context=current_context,
        budget_tokens=budget,
        focus_areas=focus,
    )

    # If entry points were found, resolve them via ProjectIndex
    if plan.entry_points:
        try:
            from .project_index import ProjectIndex
            idx = ProjectIndex.build(project, include_sources=False)
            candidates = delegator.plan_to_candidates(plan, idx)
            if candidates:
                plan_dict = plan.to_dict()
                plan_dict["resolved_candidates"] = [
                    {"symbol_id": c.symbol_id, "signature": c.signature}
                    for c in candidates
                ]
        except Exception:
            pass

    return plan.format_for_agent()


# === COHERENCE VERIFICATION ===


@mcp.tool()
def verify_coherence(
    project: str,
    files: list[str] | None = None,
) -> str:
    """Verify cross-file coherence of recent edits.

    Checks for signature mismatches, removed parameters, and import
    inconsistencies across edited files. Run before committing multi-file edits.

    Args:
        project: Project root directory
        files: Optional list of files to check (auto-detects from git if None)

    Returns:
        Formatted coherence report
    """
    from .coherence_verify import verify_from_context_pack, format_coherence_report_for_agent

    # Build a minimal pack from the files list
    pack = {"slices": [{"id": f"{f}:_"} for f in (files or [])]}
    report = verify_from_context_pack(project, pack)
    return format_coherence_report_for_agent(report)


# === DIRECT-CALL TOOLS (bypass daemon, call Python APIs directly) ===
# These tools wrap tldrs's unique capabilities that have no daemon handler yet.
# Because the MCP server is a persistent process, direct calls incur no startup cost.


@mcp.tool()
def diff_context(
    project: str = ".",
    preset: str = "compact",
    base: str | None = None,
    head: str | None = None,
    budget: int | None = None,
    language: str = "python",
    session_id: str | None = None,
    delta: bool = False,
) -> str:
    """Get git-aware diff context with symbol mapping and adaptive windowing.

    This is tldrs's flagship feature — analyzes git diffs, maps hunks to enclosing
    symbols, follows callers/callees, and returns token-efficient context.

    Presets control output shape:
    - compact: ultracompact format, 2000 token budget, import compression, no comments
    - minimal: ultracompact + two-stage block pruning + type pruning, 1500 budget
    - multi-turn: cache-friendly format with delta tracking for session continuity

    Args:
        project: Project root directory
        preset: Output preset (compact, minimal, multi-turn) — controls format/budget/compression
        base: Git base ref (default: HEAD~1)
        head: Git head ref (default: HEAD)
        budget: Override token budget from preset
        language: Programming language (python, typescript, go, rust, etc.)
        session_id: Session ID for delta caching (required for multi-turn preset)
        delta: Enable delta mode — unchanged symbols show [UNCHANGED] marker

    Returns:
        Formatted diff context string
    """
    from ...presets import PRESETS, resolve_auto_session_id
    from .engines.difflens import get_diff_context as _get_diff_context
    from .output_formats import format_context_pack

    # Apply preset defaults
    preset_config = PRESETS.get(preset, PRESETS["compact"])
    fmt = preset_config.get("format", "ultracompact")
    effective_budget = budget if budget is not None else preset_config.get("budget")
    compress = preset_config.get("compress")
    strip_comments = preset_config.get("strip_comments", False)
    compress_imports = preset_config.get("compress_imports", False)
    type_prune = preset_config.get("type_prune", False)

    # Handle session_id / delta from preset or explicit args
    effective_session_id = session_id
    effective_delta = delta
    if preset_config.get("delta") and not delta:
        effective_delta = True
    if preset_config.get("session_id") == "auto" and effective_session_id is None:
        effective_session_id = resolve_auto_session_id(project)

    if effective_delta and effective_session_id:
        from .engines.delta import get_diff_context_with_delta
        result = get_diff_context_with_delta(
            project,
            effective_session_id,
            base=base,
            head=head,
            budget_tokens=effective_budget,
            language=language,
            compress=compress,
            strip_comments=strip_comments,
            compress_imports=compress_imports,
            type_prune=type_prune,
        )
    else:
        result = _get_diff_context(
            project,
            base=base,
            head=head,
            budget_tokens=effective_budget,
            language=language,
            compress=compress,
            strip_comments=strip_comments,
            compress_imports=compress_imports,
            type_prune=type_prune,
        )

    return format_context_pack(result, fmt=fmt)


@mcp.tool()
def structural_search(
    project: str,
    pattern: str,
    language: str | None = None,
    max_results: int = 50,
) -> dict:
    """Search for structural code patterns using ast-grep (tree-sitter CSTs).

    Unlike regex search, this matches code *structure*. Use meta-variables:
    - $VAR matches any single node
    - $$$ARGS matches multiple nodes (variadic)

    Example patterns:
    - "def $FUNC($$$ARGS): $$$BODY return None" — functions that return None
    - "if $COND: $$$BODY" — all if statements
    - "$OBJ.$METHOD($$$ARGS)" — all method calls

    Args:
        project: Project root directory
        pattern: ast-grep pattern with meta-variables ($VAR, $$$ARGS)
        language: Language to search (auto-detected from extensions if None)
        max_results: Maximum number of matches to return

    Returns:
        Dict with pattern, language, and matches list
    """
    from .engines.astgrep import get_structural_search

    result = get_structural_search(
        project_path=project,
        pattern=pattern,
        language=language,
        max_results=max_results,
    )

    return {
        "pattern": result.pattern,
        "language": result.language,
        "matches": [
            {
                "file": m.file,
                "line": m.line,
                "end_line": m.end_line,
                "text": m.text,
                "meta_vars": m.meta_vars,
            }
            for m in result.matches
        ],
    }


@mcp.tool()
def distill(
    project: str,
    task: str,
    budget: int = 1500,
    session_id: str | None = None,
    language: str | None = None,
) -> str:
    """Get compressed, prescriptive context for a task.

    Distill analyzes git diffs and symbol graphs to produce a focused summary:
    files to edit, key function signatures, dependencies, and risk areas.
    Ideal for sub-agent consumption where full code isn't needed.

    Args:
        project: Project root directory
        task: Description of what you're trying to accomplish
        budget: Token budget for output (default 1500)
        session_id: Optional session ID for delta tracking
        language: Programming language (default: python)

    Returns:
        Formatted distilled context string
    """
    from .context_delegation import ContextDelegator
    from .distill_formatter import format_distilled

    delegator = ContextDelegator(Path(project))
    distilled = delegator.distill(
        project_root=project,
        task=task,
        budget=budget,
        session_id=session_id,
        language=language,
    )

    return format_distilled(distilled, budget=budget)


@mcp.tool()
def hotspots(
    project: str = ".",
    top_n: int = 20,
    since_days: int | None = None,
) -> list[dict]:
    """Show frequently accessed symbols across sessions (attention hotspots).

    Uses the attention tracking database to identify which symbols agents
    interact with most. Helps focus on high-traffic code areas.

    Requires .tldrs/attention.db to exist (created by attention_pruning module).

    Args:
        project: Project root directory
        top_n: Number of top symbols to return (default 20)
        since_days: Only include symbols accessed within this many days

    Returns:
        List of dicts with symbol_id, delivery_count, usage_count,
        popularity_score, last_delivered, last_used
    """
    from .attention_pruning import AttentionTracker

    tracker = AttentionTracker(Path(project))
    return tracker.get_hotspots(top_n=top_n, since_days=since_days)


# === DAEMON MANAGEMENT ===


@mcp.tool()
def status(project: str = ".") -> dict:
    """Get daemon status including uptime and cache statistics.

    Args:
        project: Project root directory
    """
    return _send_command(project, {"cmd": "status"})


def main():
    """Entry point for tldr-mcp command."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="TLDR MCP Server")
    parser.add_argument("--project", default=".", help="Project root directory")
    args = parser.parse_args()

    # Set default project for tools that need it
    os.environ["TLDR_PROJECT"] = str(Path(args.project).resolve())

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
