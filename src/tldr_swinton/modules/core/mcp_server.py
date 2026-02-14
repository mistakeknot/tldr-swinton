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
from typing import Annotated

from pydantic import Field

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP
    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    FastMCP = None
    _MCP_AVAILABLE = False


_INSTRUCTIONS = """\
tldr-code provides token-efficient code reconnaissance. Use these tools INSTEAD OF \
Read/Grep/Glob when you need to understand code structure without reading full files.

COST LADDER (cheapest first):
1. extract(file, compact=True) ~200 tok — file map. Use INSTEAD OF Read for overview.
2. structure(project) ~500 tok — directory symbols. Use INSTEAD OF Glob + multiple Reads.
3. context(entry) ~400 tok — call graph around symbol. Use INSTEAD OF reading caller files.
4. diff_context(project) ~800 tok — changed-code context. Use INSTEAD OF git diff + Read.
5. impact(function) ~300 tok — reverse call graph. Use BEFORE refactoring any function.
6. semantic(query) ~300 tok — meaning-based search. Use INSTEAD OF Grep for concepts.\
"""


class _NoMCP:
    def __init__(self, name: str, **kwargs) -> None:
        self.name = name

    def tool(self, **kwargs):
        def decorator(fn):
            return fn
        return decorator

mcp = FastMCP("tldr-code", instructions=_INSTRUCTIONS) if _MCP_AVAILABLE else _NoMCP("tldr-code")


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
    response = _send_raw(project, command)
    if (
        isinstance(response, dict)
        and response.get("status") == "ok"
        and "result" in response
    ):
        return response["result"]
    return response


def _format_context_result(result: dict | str, fmt: str) -> str:
    if isinstance(result, dict) and result.get("status") not in (None, "ok"):
        return str(result)
    if isinstance(result, dict) and result.get("status") == "ok":
        ctx = result.get("result", {})
    else:
        ctx = result
    if isinstance(ctx, str):
        return ctx
    if fmt in ("ultracompact", "json", "json-pretty"):
        from .output_formats import format_context_pack
        return format_context_pack(ctx, fmt=fmt)
    return str(ctx)


# === NAVIGATION TOOLS ===


@mcp.tool(description=(
    "File tree listing — paths only, no symbols. "
    "Use for initial orientation in unfamiliar projects."
))
def tree(
    project: Annotated[str, Field(description="Project root directory")] = ".",
    extensions: Annotated[list[str] | None, Field(description="Filter by extensions (e.g. [\".py\", \".ts\"])")] = None,
) -> dict:
    """Get file tree structure for a project."""
    return _send_command(
        project,
        {
            "cmd": "tree",
            "extensions": tuple(extensions) if extensions else None,
            "exclude_hidden": True,
        },
    )


@mcp.tool(description=(
    "Get all symbols (functions, classes, imports) across a directory. ~500 tokens. "
    "Use INSTEAD OF Glob + multiple Read calls to survey a codebase area."
))
def structure(
    project: Annotated[str, Field(description="Project root directory")] = ".",
    language: Annotated[str, Field(description="Programming language (python, typescript, go, rust, etc.)")] = "python",
    max_results: Annotated[int, Field(description="Maximum files to analyze")] = 100,
) -> dict:
    """Get code structure (codemaps) - functions, classes, imports per file."""
    return _send_command(
        project,
        {"cmd": "structure", "language": language, "max_results": max_results},
    )


@mcp.tool(description="Regex search across project files. Built-in Grep is usually sufficient; use this only when the daemon is already running.")
def search(
    project: Annotated[str, Field(description="Project root directory")],
    pattern: Annotated[str, Field(description="Regex pattern to search for")],
    max_results: Annotated[int, Field(description="Maximum matches to return")] = 100,
) -> dict:
    """Search files for a regex pattern."""
    return _send_command(
        project, {"cmd": "search", "pattern": pattern, "max_results": max_results}
    )


@mcp.tool(description=(
    "Get function/class signatures and line numbers from a file. "
    "With compact=True: ~200 tokens vs ~2000+ for Read. "
    "Use INSTEAD OF Read when exploring what a file contains."
))
def extract(
    file: Annotated[str, Field(description="Path to source file")],
    compact: Annotated[bool, Field(description="Return signatures+line numbers only (~87% smaller). Default False.")] = False,
) -> dict:
    """Extract code structure from a file."""
    if compact:
        from .api import compact_extract
        return compact_extract(file)
    project = str(Path(file).parent)
    return _send_command(project, {"cmd": "extract", "file": file})


# === CONTEXT TOOLS (Key differentiator - 93%+ token savings) ===


@mcp.tool(description=(
    "Follow call graph from a symbol — signatures of callees/callers at specified depth. "
    "~400 tokens vs reading all related files. "
    "Use INSTEAD OF manually tracing calls across files."
))
def context(
    project: Annotated[str, Field(description="Project root directory")],
    entry: Annotated[str, Field(description="Entry point (function_name or Class.method)")],
    preset: Annotated[str | None, Field(description="Preset (compact, minimal, agent, multi-turn). Overrides format/budget defaults.")] = None,
    depth: Annotated[int, Field(description="Call graph depth")] = 2,
    language: Annotated[str, Field(description="Programming language")] = "python",
    format: Annotated[str, Field(description="Output format (ultracompact, text, json)")] = "ultracompact",
    budget: Annotated[int | None, Field(description="Token budget (None=unlimited)")] = 4000,
    with_docs: Annotated[bool, Field(description="Include docstrings")] = False,
    session_id: Annotated[str | None, Field(description="Session ID for delta caching")] = None,
    delta: Annotated[bool, Field(description="Track unchanged symbols with [UNCHANGED] markers")] = False,
) -> str:
    """Get token-efficient LLM context starting from an entry point."""
    # Apply preset defaults (explicit params take precedence)
    if preset is not None:
        from ...presets import PRESETS, resolve_auto_session_id
        preset_config = PRESETS.get(preset, PRESETS["compact"])
        if format == "ultracompact":  # only override if still at default
            format = preset_config.get("format", format)
        if budget == 4000:  # only override if still at default
            budget = preset_config.get("budget", budget)
        if not delta and preset_config.get("delta"):
            delta = True
        if session_id is None and preset_config.get("session_id") == "auto":
            session_id = resolve_auto_session_id(project)

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


@mcp.tool(description="Control flow graph for a function — basic blocks, edges, cyclomatic complexity. Use for understanding complex branching logic.")
def cfg(
    file: Annotated[str, Field(description="Path to source file")],
    function: Annotated[str, Field(description="Function name to analyze")],
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Get control flow graph for a function."""
    project = str(Path(file).parent)
    return _send_command(
        project,
        {"cmd": "cfg", "file": file, "function": function, "language": language},
    )


@mcp.tool(description="Data flow graph for a function — variable references and def-use chains. Use for tracking how data propagates.")
def dfg(
    file: Annotated[str, Field(description="Path to source file")],
    function: Annotated[str, Field(description="Function name to analyze")],
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Get data flow graph for a function."""
    project = str(Path(file).parent)
    return _send_command(
        project,
        {"cmd": "dfg", "file": file, "function": function, "language": language},
    )


@mcp.tool(description="Program slice — lines affecting or affected by a given line. Use for understanding data dependencies within a function.")
def slice(
    file: Annotated[str, Field(description="Path to source file")],
    function: Annotated[str, Field(description="Function name")],
    line: Annotated[int, Field(description="Line number to slice from")],
    direction: Annotated[str, Field(description="'backward' (what affects this line) or 'forward' (what it affects)")] = "backward",
    variable: Annotated[str | None, Field(description="Specific variable to trace")] = None,
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Get program slice - lines affecting or affected by a given line."""
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


def _strip_impact_noise(node: dict) -> dict:
    """Remove redundant fields from impact tree nodes."""
    cleaned = {"function": node["function"], "file": node["file"]}
    if node.get("truncated"):
        cleaned["truncated"] = True
    if node.get("callers"):
        cleaned["callers"] = [_strip_impact_noise(c) for c in node["callers"]]
    return cleaned


@mcp.tool(description=(
    "Find all callers of a function (reverse call graph). ~300 tokens. "
    "Use BEFORE renaming, changing signatures, or refactoring. Shows what would break."
))
def impact(
    project: Annotated[str, Field(description="Project root directory")],
    function: Annotated[str, Field(description="Function name to find callers of")],
) -> dict:
    """Find all callers of a function (reverse call graph)."""
    result = _send_command(project, {"cmd": "impact", "func": function})
    if isinstance(result, dict) and "targets" in result:
        result["targets"] = {
            k: _strip_impact_noise(v) for k, v in result["targets"].items()
        }
    return result


@mcp.tool(description="Find unreachable (dead) code not called from entry points. Expensive — scans entire project call graph.")
def dead(
    project: Annotated[str, Field(description="Project root directory")],
    entry_points: Annotated[list[str] | None, Field(description="Entry point patterns (default: main, test_, cli)")] = None,
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Find unreachable (dead) code not called from entry points."""
    return _send_command(
        project,
        {"cmd": "dead", "entry_points": entry_points, "language": language},
    )


@mcp.tool(description="Detect architectural layers (entry/middle/leaf) and circular dependencies from call patterns. Expensive — scans entire project.")
def arch(
    project: Annotated[str, Field(description="Project root directory")],
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Detect architectural layers from call patterns."""
    return _send_command(project, {"cmd": "arch", "language": language})


@mcp.tool(description="Build full cross-file call graph. Expensive — prefer impact() or context() for targeted queries.")
def calls(
    project: Annotated[str, Field(description="Project root directory")],
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Build cross-file call graph for the project."""
    return _send_command(project, {"cmd": "calls", "language": language})


# === IMPORT ANALYSIS ===


@mcp.tool(description="Parse imports from a source file. Built-in Read is usually sufficient; use this for structured import data.")
def imports(
    file: Annotated[str, Field(description="Path to source file")],
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Parse imports from a source file."""
    project = str(Path(file).parent)
    return _send_command(
        project, {"cmd": "imports", "file": file, "language": language}
    )


@mcp.tool(description=(
    "Find all files that import a given module. "
    "Use BEFORE renaming or moving a module to know what breaks."
))
def importers(
    project: Annotated[str, Field(description="Project root directory")],
    module: Annotated[str, Field(description="Module name to search for")],
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Find all files that import a given module."""
    return _send_command(
        project, {"cmd": "importers", "module": module, "language": language}
    )


# === SEMANTIC SEARCH ===


@mcp.tool(description=(
    "Search code by meaning using embeddings. ~300 tokens. "
    "Finds related functions/classes even without exact keywords. "
    "Use INSTEAD OF Grep when searching for a concept rather than literal text."
))
def semantic(
    project: Annotated[str, Field(description="Project root directory")],
    query: Annotated[str, Field(description="Natural language query (e.g. 'authentication logic')")],
    k: Annotated[int, Field(description="Number of results to return")] = 10,
) -> dict:
    """Semantic code search using embeddings."""
    return _send_command(
        project, {"cmd": "semantic", "action": "search", "query": query, "k": k}
    )


# === QUALITY TOOLS ===


@mcp.tool(description=(
    "Run type checker + linter (pyright + ruff for Python). "
    "Validate changes before committing."
))
def diagnostics(
    path: Annotated[str, Field(description="File or directory path")],
    language: Annotated[str, Field(description="Programming language")] = "python",
) -> dict:
    """Get type and lint diagnostics."""
    project = str(Path(path).parent) if Path(path).is_file() else path
    return _send_command(
        project, {"cmd": "diagnostics", "file": path, "language": language}
    )


@mcp.tool(description=(
    "Find tests affected by changed files via call graph. "
    "Run only relevant tests after edits instead of the full suite."
))
def change_impact(
    project: Annotated[str, Field(description="Project root directory")],
    files: Annotated[list[str] | None, Field(description="Changed files (auto-detects from git if None)")] = None,
) -> dict:
    """Find tests affected by changed files."""
    return _send_command(project, {"cmd": "change_impact", "files": files})


# === CONTEXT DELEGATION ===


@mcp.tool(description=(
    "Get a prioritized retrieval plan for a complex task instead of fetching all context upfront. "
    "Reduces wasted retrieval by 50%+. Returns ordered steps to execute."
))
def delegate(
    project: Annotated[str, Field(description="Project root directory")],
    task: Annotated[str, Field(description="What you're trying to accomplish")],
    current_context: Annotated[list[str] | None, Field(description="Symbols already retrieved (avoids re-retrieval)")] = None,
    budget: Annotated[int, Field(description="Maximum tokens for context")] = 8000,
    focus: Annotated[list[str] | None, Field(description="Specific files/modules to focus on")] = None,
) -> str:
    """Get an incremental context retrieval plan instead of raw context."""
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


@mcp.tool(description=(
    "Check cross-file consistency after multi-file edits — signature mismatches, missing imports. "
    "Run BEFORE committing when you've changed function signatures or moved code."
))
def verify_coherence(
    project: Annotated[str, Field(description="Project root directory")],
    files: Annotated[list[str] | None, Field(description="Files to check (auto-detects from git if None)")] = None,
) -> str:
    """Verify cross-file coherence of recent edits."""
    from .coherence_verify import verify_from_context_pack, format_coherence_report_for_agent

    # Build a minimal pack from the files list
    pack = {"slices": [{"id": f"{f}:_"} for f in (files or [])]}
    report = verify_from_context_pack(project, pack)
    return format_coherence_report_for_agent(report)


# === DIRECT-CALL TOOLS (bypass daemon, call Python APIs directly) ===
# These tools wrap tldrs's unique capabilities that have no daemon handler yet.
# Because the MCP server is a persistent process, direct calls incur no startup cost.


@mcp.tool(description=(
    "Git-aware context for recent changes — maps diff hunks to symbols, follows callers. "
    "~800 tokens vs ~4000+ for git diff + Read. "
    "Start here for any task involving recently modified code."
))
def diff_context(
    project: Annotated[str, Field(description="Project root directory")] = ".",
    preset: Annotated[str, Field(description="Output preset (compact, minimal, multi-turn)")] = "compact",
    base: Annotated[str | None, Field(description="Git base ref (default: HEAD~1)")] = None,
    head: Annotated[str | None, Field(description="Git head ref (default: HEAD)")] = None,
    budget: Annotated[int | None, Field(description="Override token budget from preset")] = None,
    language: Annotated[str, Field(description="Programming language")] = "python",
    session_id: Annotated[str | None, Field(description="Session ID for delta caching")] = None,
    delta: Annotated[bool, Field(description="Track unchanged symbols with [UNCHANGED] markers")] = False,
    max_lines: Annotated[int | None, Field(description="Cap output at N lines")] = None,
    max_bytes: Annotated[int | None, Field(description="Cap output at N bytes")] = None,
) -> str:
    """Get git-aware diff context with symbol mapping and adaptive windowing."""
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

    result_text = format_context_pack(result, fmt=fmt)

    if max_lines is not None or max_bytes is not None:
        from .output_formats import truncate_output
        result_text = truncate_output(result_text, max_lines=max_lines, max_bytes=max_bytes)

    return result_text


@mcp.tool(description=(
    "Search for AST patterns using tree-sitter. Matches code structure, not text. "
    "Use INSTEAD OF Grep for queries like 'functions returning None' or 'all method calls'. "
    "Meta-variables: $VAR=any node, $$$ARGS=variadic. "
    "Example: 'def $FUNC($$$ARGS): return None'"
))
def structural_search(
    project: Annotated[str, Field(description="Project root directory")],
    pattern: Annotated[str, Field(description="ast-grep pattern with meta-variables ($VAR, $$$ARGS)")],
    language: Annotated[str | None, Field(description="Language (auto-detected if None)")] = None,
    max_results: Annotated[int, Field(description="Maximum matches to return")] = 50,
) -> dict:
    """Search for structural code patterns using ast-grep (tree-sitter CSTs)."""
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


@mcp.tool(description=(
    "Compressed prescriptive context for a task — files to edit, key signatures, risks. "
    "Ideal for sub-agent handoff or when you need a plan before diving into code."
))
def distill(
    project: Annotated[str, Field(description="Project root directory")],
    task: Annotated[str, Field(description="What you're trying to accomplish")],
    budget: Annotated[int, Field(description="Token budget for output")] = 1500,
    session_id: Annotated[str | None, Field(description="Session ID for delta tracking")] = None,
    language: Annotated[str | None, Field(description="Programming language")] = None,
) -> str:
    """Get compressed, prescriptive context for a task."""
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


@mcp.tool(description="Show most-accessed symbols across sessions. Requires .tldrs/attention.db. Admin/debugging tool.")
def hotspots(
    project: Annotated[str, Field(description="Project root directory")] = ".",
    top_n: Annotated[int, Field(description="Number of top symbols to return")] = 20,
    since_days: Annotated[int | None, Field(description="Only symbols accessed within N days")] = None,
) -> list[dict]:
    """Show frequently accessed symbols across sessions (attention hotspots)."""
    from .attention_pruning import AttentionTracker

    tracker = AttentionTracker(Path(project))
    return tracker.get_hotspots(top_n=top_n, since_days=since_days)


# === DAEMON MANAGEMENT ===


@mcp.tool(description="Daemon status — uptime and cache statistics. Admin/debugging tool.")
def status(
    project: Annotated[str, Field(description="Project root directory")] = ".",
) -> dict:
    """Get daemon status including uptime and cache statistics."""
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
