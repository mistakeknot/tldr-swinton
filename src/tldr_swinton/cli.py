#!/usr/bin/env python3
"""
TLDR-Swinton CLI - Token-efficient code analysis for LLMs.

A fork of llm-tldr with improved TypeScript and Rust support.

Usage:
    tldrs tree [path]                    Show file tree
    tldrs structure [path]               Show code structure (codemaps)
    tldrs search <pattern> [path]        Search files for pattern
    tldrs extract <file>                 Extract full file info
    tldrs context <entry> [--project]    Get relevant context for LLM
    tldrs cfg <file> <function>          Control flow graph
    tldrs dfg <file> <function>          Data flow graph
    tldrs slice <file> <func> <line>     Program slice
"""
import argparse
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .modules.core.state_store import StateStore


def _machine_output(result: dict | list, args) -> None:
    """Print result in machine-readable format if --machine flag is set.

    For --machine mode, wraps result in success envelope:
    {"success": true, "result": <result>}

    Otherwise prints with standard indentation.
    """
    if getattr(args, "machine", False):
        wrapped = {"success": True, "result": result}
        print(json.dumps(wrapped, separators=(",", ":"), ensure_ascii=False))
    else:
        print(json.dumps(result, indent=2))


def _get_subprocess_detach_kwargs():
    """Get platform-specific kwargs for detaching subprocess."""
    import subprocess
    if os.name == 'nt':  # Windows
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    else:  # Unix (Mac/Linux)
        return {'start_new_session': True}


def _vhs_command() -> list[str]:
    override = os.environ.get("TLDRS_VHS_CMD")
    if override:
        return override.split()
    return ["tldrs-vhs"]


def _vhs_env() -> dict:
    env = os.environ.copy()
    extra_path = env.get("TLDRS_VHS_PYTHONPATH")
    if extra_path:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = f"{extra_path}:{existing}" if existing else extra_path
    return env


def _vhs_available() -> bool:
    import shutil
    override = os.environ.get("TLDRS_VHS_CMD")
    if override:
        return True
    return shutil.which("tldrs-vhs") is not None


def _get_state_store(project_root: Path) -> StateStore:
    return StateStore(project_root)


def _vhs_put(text: str, project_root: Path) -> str:
    store = _get_state_store(project_root)
    data = text.encode("utf-8")
    return store.vhs.put(io.BytesIO(data))


def _vhs_get(ref: str, project_root: Path) -> str:
    store = _get_state_store(project_root)
    with tempfile.NamedTemporaryFile() as tmp:
        store.vhs.get(ref, out=Path(tmp.name))
        tmp.seek(0)
        return tmp.read().decode("utf-8")


def _make_vhs_summary(ctx) -> str:
    files = {func.file for func in ctx.functions if func.file}
    return (
        f"Entry {ctx.entry_point} depth={ctx.depth} "
        f"functions={len(ctx.functions)} files={len(files)}"
    )


def _make_vhs_preview(text: str, max_lines: int = 30, max_bytes: int = 2048) -> str:
    lines: list[str] = []
    used = 0
    for line in text.splitlines():
        if len(lines) >= max_lines:
            break
        line_bytes = len((line + "\n").encode("utf-8"))
        if used + line_bytes > max_bytes:
            break
        lines.append(line)
        used += line_bytes
    return "\n".join(lines)


def _get_context_pack_with_delta(
    project: str,
    entry_point: str,
    session_id: str,
    depth: int = 2,
    language: str = "python",
    budget_tokens: int | None = None,
    include_docstrings: bool = False,
) -> "ContextPack":
    """Get context pack with delta detection against session cache.

    Uses delta-first extraction: gets signatures first, checks delta,
    then only extracts code for changed symbols. This avoids wasted
    extraction for unchanged symbols.

    Returns a ContextPack where unchanged symbols have code=None and are
    listed in the `unchanged` field. Changed/new symbols include full code.
    """
    import hashlib
    from .modules.core.engines.symbolkite import get_signatures_for_entry
    from .modules.core.contextpack_engine import Candidate, ContextPack, ContextPackEngine

    project_root = Path(project).resolve()
    store = _get_state_store(project_root)

    # DELTA-FIRST: Get signatures only (no code extraction yet)
    signatures_result = get_signatures_for_entry(
        project,
        entry_point,
        depth=depth,
        language=language,
        disambiguate=True,
    )

    # Handle error case (ambiguous)
    if isinstance(signatures_result, dict) and signatures_result.get("error"):
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    signatures = signatures_result
    if not signatures:
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    # Compute ETags from signatures only (not code)
    # For context packs, we use signature-based ETags since code may vary
    symbol_etags = {}
    for sig in signatures:
        content = sig.signature
        etag = hashlib.sha256(content.encode()).hexdigest()
        symbol_etags[sig.symbol_id] = etag

    # Check delta against session cache
    delta_result = store.check_delta(session_id, symbol_etags)

    # Now extract code ONLY for changed symbols
    from .modules.core.api import get_symbol_context_pack

    # If all symbols unchanged, return early with signatures only
    if not delta_result.changed:
        candidates = [
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=max(1, (depth - sig.depth) + 1),
                relevance_label=f"depth_{sig.depth}",
                order=i,
                signature=sig.signature,
                code=None,  # All unchanged - no code needed
                lines=(sig.line, sig.line) if sig.line else None,
                meta={"calls": sig.calls},
            )
            for i, sig in enumerate(signatures)
        ]

        engine = ContextPackEngine()
        pack = engine.build_context_pack_delta(
            candidates,
            delta_result,
            budget_tokens=budget_tokens,
        )
        return pack

    # Some symbols changed - need to get full pack for code extraction
    # but we can now be selective about what we include
    full_pack_dict = get_symbol_context_pack(
        project,
        entry_point,
        depth=depth,
        language=language,
        budget_tokens=None,  # Get all symbols first
        include_docstrings=include_docstrings,
    )

    # Handle ambiguous case
    if full_pack_dict.get("error"):
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    slices_data = full_pack_dict.get("slices", [])
    if not slices_data:
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    # Build candidates with code only for changed symbols
    slice_map = {s["id"]: s for s in slices_data}
    candidates = []

    for i, sig in enumerate(signatures):
        is_changed = sig.symbol_id in delta_result.changed
        slice_data = slice_map.get(sig.symbol_id, {})

        candidates.append(
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=_relevance_to_int(slice_data.get("relevance")) or max(1, (depth - sig.depth) + 1),
                relevance_label=slice_data.get("relevance") or f"depth_{sig.depth}",
                order=i,
                signature=sig.signature,
                code=slice_data.get("code") if is_changed else None,  # Only include code for changed
                lines=tuple(slice_data["lines"]) if slice_data.get("lines") else None,
                meta=slice_data.get("meta") or {"calls": sig.calls},
            )
        )

    engine = ContextPackEngine()
    delta_pack = engine.build_context_pack_delta(
        candidates,
        delta_result,
        budget_tokens=budget_tokens,
    )

    # Record deliveries for changed symbols
    deliveries = []
    for s in delta_pack.slices:
        if s.id in (delta_pack.unchanged or []):
            continue
        deliveries.append({
            "symbol_id": s.id,
            "etag": symbol_etags.get(s.id, ""),
            "representation": "full" if s.code else "signature",
            "vhs_ref": None,
            "token_estimate": len(s.code) // 4 if s.code else len(s.signature) // 4,
        })

    if deliveries:
        from .modules.core.state_store import _compute_repo_fingerprint
        fingerprint = _compute_repo_fingerprint(project_root)
        store.open_session(session_id, fingerprint, language)
        store.record_deliveries_batch(session_id, deliveries)

    return delta_pack


def _relevance_to_int(label: str | None) -> int:
    """Convert relevance label to integer for sorting."""
    if not label:
        return 0
    mapping = {
        "contains_diff": 100,
        "caller": 80,
        "callee": 80,
        "test": 60,
        "signature_only": 20,
    }
    return mapping.get(label, 50)


def _get_diff_context_with_delta(
    project: Path,
    session_id: str,
    base: str | None = None,
    head: str = "HEAD",
    budget_tokens: int | None = None,
    language: str = "python",
    compress: str | None = None,
) -> "ContextPack":
    """Get diff context pack with delta detection against session cache.

    Uses delta-first extraction: parses diff hunks, gets signatures first,
    checks delta, then only extracts code for changed symbols. This avoids
    wasted extraction for unchanged symbols.

    Returns a ContextPack where unchanged symbols have code=None and are
    listed in the `unchanged` field. Changed/new symbols include full code.

    This is where delta mode provides real savings - diff-context includes
    code bodies, so skipping unchanged code saves significant tokens.
    """
    import hashlib
    import subprocess
    from .modules.core.engines.difflens import parse_unified_diff, get_diff_signatures
    from .modules.core.contextpack_engine import Candidate, ContextPack, ContextPackEngine

    project_root = project.resolve()
    store = _get_state_store(project_root)

    # Parse diff to get hunks
    base_ref = base or "HEAD~1"
    head_ref = head or "HEAD"

    def _run_diff(args: list[str]) -> str:
        result = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--unified=0"] + args,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout

    diff_text = _run_diff([f"{base_ref}..{head_ref}"])
    diff_text += _run_diff(["--staged"])
    diff_text += _run_diff([])

    hunks = parse_unified_diff(diff_text)
    if not hunks:
        # Fallback to recent files
        from .modules.core.api import get_diff_context
        full_pack = get_diff_context(
            project_root,
            base=base,
            head=head,
            budget_tokens=budget_tokens,
            language=language,
            compress=compress,
        )
        return ContextPack(
            slices=[],
            unchanged=[],
            rehydrate={},
            budget_used=full_pack.get("budget_used", 0),
        )

    # DELTA-FIRST: Get signatures only (no code extraction yet)
    signatures = get_diff_signatures(project_root, hunks, language=language)

    if not signatures:
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    # Compute ETags from signature + diff_lines (which identifies what changed)
    symbol_etags = {}
    for sig in signatures:
        # Include diff lines in etag so changes to the symbol's diff portion are detected
        content = f"{sig.signature}\n{','.join(map(str, sig.diff_lines))}"
        etag = hashlib.sha256(content.encode()).hexdigest()
        symbol_etags[sig.symbol_id] = etag

    # Check delta against session cache
    delta_result = store.check_delta(session_id, symbol_etags)

    # If all symbols unchanged, return early with signatures only
    if not delta_result.changed:
        relevance_score = {"contains_diff": 100, "caller": 80, "callee": 80, "adjacent": 50}
        candidates = [
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=relevance_score.get(sig.relevance_label, 50),
                relevance_label=sig.relevance_label,
                order=i,
                signature=sig.signature,
                code=None,  # All unchanged - no code needed
                lines=(sig.line, sig.line) if sig.line else None,
                meta={"diff_lines": sig.diff_lines},
            )
            for i, sig in enumerate(signatures)
        ]

        engine = ContextPackEngine()
        pack = engine.build_context_pack_delta(
            candidates,
            delta_result,
            budget_tokens=budget_tokens,
        )
        return pack

    # Some symbols changed - need to get full pack for code extraction
    from .modules.core.api import get_diff_context

    full_pack_dict = get_diff_context(
        project_root,
        base=base,
        head=head,
        budget_tokens=None,  # Get all symbols first
        language=language,
        compress=compress,
    )

    slices_data = full_pack_dict.get("slices", [])

    # Build slice lookup
    slice_map = {s["id"]: s for s in slices_data}

    # Build candidates with code only for changed symbols
    relevance_score = {"contains_diff": 100, "caller": 80, "callee": 80, "adjacent": 50}
    candidates = []

    for i, sig in enumerate(signatures):
        is_changed = sig.symbol_id in delta_result.changed
        slice_data = slice_map.get(sig.symbol_id, {})

        candidates.append(
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=_relevance_to_int(slice_data.get("relevance")) or relevance_score.get(sig.relevance_label, 50),
                relevance_label=slice_data.get("relevance") or sig.relevance_label,
                order=i,
                signature=sig.signature,
                code=slice_data.get("code") if is_changed else None,  # Only include code for changed
                lines=tuple(slice_data["lines"]) if slice_data.get("lines") and len(slice_data["lines"]) == 2 else None,
                meta={k: v for k, v in slice_data.items() if k not in ("id", "relevance", "signature", "code", "lines")} or {"diff_lines": sig.diff_lines},
            )
        )

    engine = ContextPackEngine()
    delta_pack = engine.build_context_pack_delta(
        candidates,
        delta_result,
        budget_tokens=budget_tokens,
    )

    # Record deliveries for changed symbols
    deliveries = []
    for s in delta_pack.slices:
        if s.id in (delta_pack.unchanged or []):
            continue
        deliveries.append({
            "symbol_id": s.id,
            "etag": symbol_etags.get(s.id, ""),
            "representation": "full" if s.code else "signature",
            "vhs_ref": None,
            "token_estimate": len(s.code) // 4 if s.code else len(s.signature) // 4,
        })

    if deliveries:
        from .modules.core.state_store import _compute_repo_fingerprint
        fingerprint = _compute_repo_fingerprint(project_root)
        store.open_session(session_id, fingerprint, language)
        store.record_deliveries_batch(session_id, deliveries)

    return delta_pack


def _render_vhs_output(ref: str, summary: str, preview: str) -> str:
    lines = [ref, f"# Summary: {summary}", "# Preview:"]
    if preview:
        lines.append(preview)
    return "\n".join(lines)


def _git_ref_exists(project: Path, ref: str) -> bool:
    import subprocess
    result = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--verify", ref],
        text=True,
        capture_output=True,
    )
    return result.returncode == 0


def _git_merge_base(project: Path, ref: str) -> str | None:
    import subprocess
    result = subprocess.run(
        ["git", "-C", str(project), "merge-base", "HEAD", ref],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _resolve_diff_base(project: Path) -> str:
    for ref in ("main", "master"):
        if _git_ref_exists(project, ref):
            merge_base = _git_merge_base(project, ref)
            if merge_base:
                return merge_base
    return "HEAD~1"


# Extension to language mapping for auto-detection
EXTENSION_TO_LANGUAGE = {
    '.java': 'java',
    '.py': 'python',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.go': 'go',
    '.rs': 'rust',
    '.c': 'c',
    '.h': 'c',
    '.cpp': 'cpp',
    '.hpp': 'cpp',
    '.cc': 'cpp',
    '.cxx': 'cpp',
    '.hh': 'cpp',
    '.rb': 'ruby',
    '.php': 'php',
    '.swift': 'swift',
    '.cs': 'csharp',
    '.kt': 'kotlin',
    '.kts': 'kotlin',
    '.scala': 'scala',
    '.sc': 'scala',
    '.lua': 'lua',
    '.ex': 'elixir',
    '.exs': 'elixir',
}


def detect_language_from_extension(file_path: str) -> str:
    """Detect programming language from file extension.

    Args:
        file_path: Path to the source file

    Returns:
        Language name (defaults to 'python' if unknown)
    """
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext, 'python')


def _show_first_run_tip():
    """Show a one-time tip about Swift support on first run."""
    marker = Path.home() / ".tldrs_first_run"
    if marker.exists():
        return

    # Check if Swift is already installed
    try:
        import tree_sitter_swift
        # Swift already works, no tip needed
        marker.touch()
        return
    except ImportError:
        pass

    # Show tip
    import sys
    print("Tip: For Swift support, run: python -m tldr_swinton.install_swift", file=sys.stderr)
    print("     (This message appears once)", file=sys.stderr)
    print(file=sys.stderr)

    marker.touch()


def main():
    _show_first_run_tip()
    parser = argparse.ArgumentParser(
        prog="tldrs",
        description="Token-efficient code analysis for LLMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Version: %(prog)s """ + __version__ + """

Examples:
    tldrs tree src/                      # File tree for src/
    tldrs structure . --lang python      # Code structure for Python files
    tldrs search "def process" .         # Search for pattern
    tldrs extract src/main.py            # Full file analysis
    tldrs context main --project .       # LLM context starting from main()
    tldrs cfg src/main.py process        # Control flow for process()
    tldrs slice src/main.py func 42      # Lines affecting line 42

Ignore Patterns:
    tldrs respects .tldrsignore files (gitignore syntax).
    Legacy .tldrignore is also supported (auto-migrated on first run).
    First run creates .tldrsignore with sensible defaults.
    Use --no-ignore to bypass ignore patterns.
    Use --respect-gitignore to also apply .gitignore patterns.

Daemon:
    tldrs runs a per-project daemon for fast repeated queries.
    - Socket: /tmp/tldr-{hash}.sock (hash from project path)
    - Auto-shutdown: 30 minutes idle
    - Memory: ~50-100MB base, +500MB-1GB with semantic search

    Start explicitly:  tldrs daemon start
    Check status:      tldrs daemon status
    Stop:              tldrs daemon stop

Semantic Search:
    First run downloads embedding model (1.3GB default).
    Use --model all-MiniLM-L6-v2 for smaller 80MB model.
    Set TLDR_AUTO_DOWNLOAD=1 to skip download prompts.
        """,
    )

    # Global flags
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--no-ignore",
        action="store_true",
        help="Ignore .tldrsignore patterns (include all files)",
    )
    parser.add_argument(
        "--respect-gitignore",
        action="store_true",
        help="Also respect .gitignore patterns (opt-in)",
    )
    parser.add_argument(
        "--machine",
        action="store_true",
        help="Machine-readable output (forces JSON with consistent schema and error codes)",
    )

    # Shell completion support
    try:
        import shtab
        shtab.add_argument_to(parser, ["--print-completion", "-s"])
    except ImportError:
        pass  # shtab is optional

    subparsers = parser.add_subparsers(dest="command", required=True)

    # tldr tree [path]
    tree_p = subparsers.add_parser("tree", help="Show file tree")
    tree_p.add_argument("path", nargs="?", default=".", help="Directory to scan")
    tree_p.add_argument(
        "--ext", nargs="+", help="Filter by extensions (e.g., --ext .py .ts)"
    )
    tree_p.add_argument(
        "--show-hidden", action="store_true", help="Include hidden files"
    )

    # tldr structure [path]
    struct_p = subparsers.add_parser("structure", help="Show code structure (codemaps)")
    struct_p.add_argument("path", nargs="?", default=".", help="Directory to analyze")
    struct_p.add_argument(
        "--lang",
        default="python",
        choices=["python", "typescript", "javascript", "go", "rust", "java", "c",
                 "cpp", "ruby", "php", "kotlin", "swift", "csharp", "scala", "lua", "elixir"],
        help="Language to analyze",
    )
    struct_p.add_argument(
        "--max", type=int, default=50, help="Max files to analyze (default: 50)"
    )

    # tldr search <pattern> [path]
    search_p = subparsers.add_parser("search", help="Search files for pattern")
    search_p.add_argument("pattern", help="Regex pattern to search")
    search_p.add_argument("path", nargs="?", default=".", help="Directory to search")
    search_p.add_argument("--ext", nargs="+", help="Filter by extensions")
    search_p.add_argument(
        "-C", "--context", type=int, default=0, help="Context lines around match"
    )
    search_p.add_argument(
        "--max", type=int, default=100, help="Max results (default: 100, 0=unlimited)"
    )
    search_p.add_argument(
        "--max-files", type=int, default=10000, help="Max files to scan (default: 10000)"
    )

    # tldr extract <file> [--class X] [--function Y] [--method Class.method]
    extract_p = subparsers.add_parser("extract", help="Extract full file info")
    extract_p.add_argument("file", help="File to analyze")
    extract_p.add_argument("--class", dest="filter_class", help="Filter to specific class")
    extract_p.add_argument("--function", dest="filter_function", help="Filter to specific function")
    extract_p.add_argument("--method", dest="filter_method", help="Filter to specific method (Class.method)")

    # tldr context <entry>
    ctx_p = subparsers.add_parser("context", help="Get relevant context for LLM")
    ctx_p.add_argument("entry", help="Entry point (function_name or Class.method)")
    ctx_p.add_argument("--project", default=".", help="Project root directory")
    ctx_p.add_argument("--depth", type=int, default=2, help="Call depth (default: 2)")
    ctx_p.add_argument(
        "--format",
        choices=["text", "ultracompact", "cache-friendly"],
        default="text",
        help="Output format",
    )
    ctx_p.add_argument(
        "--budget",
        type=int,
        default=None,
        help="Approx token budget for output (optional)",
    )
    ctx_p.add_argument(
        "--with-docs",
        action="store_true",
        help="Include docstrings in output",
    )
    ctx_p.add_argument(
        "--output",
        choices=["stdout", "vhs"],
        default="stdout",
        help="Output target (stdout or vhs ref)",
    )
    ctx_p.add_argument(
        "--include",
        action="append",
        default=[],
        help="Append vhs:// refs to output (may repeat)",
    )
    ctx_p.add_argument(
        "--lang",
        default="python",
        choices=["python", "typescript", "javascript", "go", "rust", "java", "c",
                 "cpp", "ruby", "php", "kotlin", "swift", "csharp", "scala", "lua", "elixir"],
        help="Language",
    )
    ctx_p.add_argument(
        "--session-id",
        default=None,
        help="Session ID for ETag caching (enables delta mode)",
    )
    ctx_p.add_argument(
        "--delta",
        action="store_true",
        help="Enable delta mode (return UNCHANGED for cached symbols)",
    )
    ctx_p.add_argument(
        "--no-delta",
        action="store_true",
        help="Disable delta mode even if session-id is provided",
    )

    ctx_p.add_argument("--max-lines", type=int, default=None, help="Cap output at N lines")
    ctx_p.add_argument("--max-bytes", type=int, default=None, help="Cap output at N bytes")

    diff_p = subparsers.add_parser("diff-context", help="Diff-first context pack")
    diff_p.add_argument("--project", default=".", help="Project root directory")
    diff_p.add_argument("--base", default=None, help="Base ref (default: merge-base with main/master)")
    diff_p.add_argument("--head", default="HEAD", help="Head ref (default: HEAD)")
    diff_p.add_argument("--budget", type=int, default=None, help="Approx token budget for output")
    diff_p.add_argument(
        "--compress",
        choices=["none", "two-stage", "chunk-summary"],
        default="none",
        help="Experimental compression mode (default: none)",
    )
    diff_p.add_argument(
        "--format",
        choices=["ultracompact", "json", "json-pretty", "cache-friendly"],
        default="ultracompact",
        help="Output format (default: ultracompact)",
    )
    diff_p.add_argument(
        "--lang",
        default="python",
        choices=["python", "typescript", "javascript", "go", "rust", "java", "c",
                 "cpp", "ruby", "php", "kotlin", "swift", "csharp", "scala", "lua", "elixir"],
        help="Language",
    )
    diff_p.add_argument(
        "--session-id",
        default=None,
        help="Session ID for delta caching (enables delta mode)",
    )
    diff_p.add_argument(
        "--delta",
        action="store_true",
        help="Enable delta mode with auto-generated session ID",
    )
    diff_p.add_argument(
        "--no-delta",
        action="store_true",
        help="Disable delta mode even if session-id provided",
    )

    diff_p.add_argument("--max-lines", type=int, default=None, help="Cap output at N lines")
    diff_p.add_argument("--max-bytes", type=int, default=None, help="Cap output at N bytes")

    # tldr cfg <file> <function>
    cfg_p = subparsers.add_parser("cfg", help="Control flow graph")
    cfg_p.add_argument("file", help="Source file")
    cfg_p.add_argument("function", help="Function name")
    cfg_p.add_argument("--lang", default=None, help="Language (auto-detected from extension if not specified)")

    # tldr dfg <file> <function>
    dfg_p = subparsers.add_parser("dfg", help="Data flow graph")
    dfg_p.add_argument("file", help="Source file")
    dfg_p.add_argument("function", help="Function name")
    dfg_p.add_argument("--lang", default=None, help="Language (auto-detected from extension if not specified)")

    # tldr slice <file> <function> <line>
    slice_p = subparsers.add_parser("slice", help="Program slice")
    slice_p.add_argument("file", help="Source file")
    slice_p.add_argument("function", help="Function name")
    slice_p.add_argument("line", type=int, help="Line number to slice from")
    slice_p.add_argument(
        "--direction",
        default="backward",
        choices=["backward", "forward"],
        help="Slice direction",
    )
    slice_p.add_argument("--var", help="Variable to track (optional)")
    slice_p.add_argument("--lang", default=None, help="Language (auto-detected from extension if not specified)")
    slice_p.add_argument("--max-lines", type=int, default=None, help="Cap output at N lines")
    slice_p.add_argument("--max-bytes", type=int, default=None, help="Cap output at N bytes")

    # tldr calls <path>
    calls_p = subparsers.add_parser("calls", help="Build cross-file call graph")
    calls_p.add_argument("path", nargs="?", default=".", help="Project root")
    calls_p.add_argument("--lang", default="python", help="Language")

    # tldr impact <func> [path]
    impact_p = subparsers.add_parser(
        "impact", help="Find all callers of a function (reverse call graph)"
    )
    impact_p.add_argument("func", help="Function name to find callers of")
    impact_p.add_argument("path", nargs="?", default=".", help="Project root")
    impact_p.add_argument("--depth", type=int, default=3, help="Max depth (default: 3)")
    impact_p.add_argument("--file", help="Filter by file containing this string")
    impact_p.add_argument("--lang", default="python", help="Language")

    # tldr dead [path]
    dead_p = subparsers.add_parser("dead", help="Find unreachable (dead) code")
    dead_p.add_argument("path", nargs="?", default=".", help="Project root")
    dead_p.add_argument(
        "--entry", nargs="*", default=[], help="Additional entry point patterns"
    )
    dead_p.add_argument("--lang", default="python", help="Language")

    # tldr arch [path]
    arch_p = subparsers.add_parser(
        "arch", help="Detect architectural layers from call patterns"
    )
    arch_p.add_argument("path", nargs="?", default=".", help="Project root")
    arch_p.add_argument("--lang", default="python", help="Language")

    # tldr imports <file>
    imports_p = subparsers.add_parser(
        "imports", help="Parse imports from a source file"
    )
    imports_p.add_argument("file", help="Source file to analyze")
    imports_p.add_argument("--lang", default=None, help="Language (auto-detected from extension if not specified)")

    # tldr importers <module> [path]
    importers_p = subparsers.add_parser(
        "importers", help="Find all files that import a module (reverse import lookup)"
    )
    importers_p.add_argument("module", help="Module name to search for importers")
    importers_p.add_argument("path", nargs="?", default=".", help="Project root")
    importers_p.add_argument("--lang", default="python", help="Language")

    # tldr change-impact [files...]
    impact_p = subparsers.add_parser(
        "change-impact", help="Find tests affected by changed files"
    )
    impact_p.add_argument(
        "files", nargs="*", help="Files to analyze (default: auto-detect from session/git)"
    )
    impact_p.add_argument(
        "--session", action="store_true", help="Use session-modified files (dirty_flag)"
    )
    impact_p.add_argument(
        "--git", action="store_true", help="Use git diff to find changed files"
    )
    impact_p.add_argument(
        "--git-base", default="HEAD~1", help="Git ref to diff against (default: HEAD~1)"
    )
    impact_p.add_argument("--lang", default="python", help="Language")
    impact_p.add_argument(
        "--depth", type=int, default=5, help="Max call graph depth (default: 5)"
    )
    impact_p.add_argument(
        "--run", action="store_true", help="Actually run the affected tests"
    )

    # tldr diagnostics <file|path>
    diag_p = subparsers.add_parser(
        "diagnostics", help="Get type and lint diagnostics"
    )
    diag_p.add_argument("target", help="File or project directory to check")
    diag_p.add_argument(
        "--project", action="store_true", help="Check entire project (default: single file)"
    )
    diag_p.add_argument(
        "--no-lint", action="store_true", help="Skip linter, only run type checker"
    )
    diag_p.add_argument(
        "--format", choices=["json", "text"], default="json", help="Output format"
    )
    diag_p.add_argument("--lang", default=None, help="Override language detection")

    # tldr warm <path>
    warm_p = subparsers.add_parser(
        "warm", help="Pre-build call graph cache for faster queries"
    )
    warm_p.add_argument("path", help="Project root directory")
    warm_p.add_argument(
        "--background", action="store_true", help="Build in background process"
    )
    warm_p.add_argument("--lang", default="python", help="Language")

    # tldr semantic index <path> / tldr semantic search <query>
    semantic_p = subparsers.add_parser(
        "semantic", help="Semantic code search using embeddings"
    )
    semantic_sub = semantic_p.add_subparsers(dest="action", required=True)

    # tldr semantic index [path]
    index_p = semantic_sub.add_parser("index", help="Build semantic index for project")
    index_p.add_argument("path", nargs="?", default=".", help="Project root")
    index_p.add_argument("--lang", default="python", help="Language")
    index_p.add_argument(
        "--model",
        default=None,
        help="Embedding model: bge-large-en-v1.5 (1.3GB, default) or all-MiniLM-L6-v2 (80MB)",
    )

    # tldr semantic search <query>
    search_p = semantic_sub.add_parser("search", help="Search semantically")
    search_p.add_argument("query", help="Natural language query")
    search_p.add_argument("--path", default=".", help="Project root")
    search_p.add_argument("--k", type=int, default=5, help="Number of results")
    search_p.add_argument("--expand", action="store_true", help="Include call graph expansion")
    search_p.add_argument("--lang", default="python", help="Language")
    search_p.add_argument(
        "--model",
        default=None,
        help="Embedding model (uses index model if not specified)",
    )

    # tldr daemon start/stop/status/query
    daemon_p = subparsers.add_parser(
        "daemon", help="Daemon management subcommands"
    )
    daemon_sub = daemon_p.add_subparsers(dest="action", required=True)

    # tldr daemon start [--project PATH]
    daemon_start_p = daemon_sub.add_parser("start", help="Start daemon for project (background)")
    daemon_start_p.add_argument("--project", "-p", default=".", help="Project path (default: current directory)")

    # tldr daemon stop [--project PATH]
    daemon_stop_p = daemon_sub.add_parser("stop", help="Stop daemon gracefully")
    daemon_stop_p.add_argument("--project", "-p", default=".", help="Project path (default: current directory)")

    # tldr daemon status [--project PATH]
    daemon_status_p = daemon_sub.add_parser("status", help="Check if daemon running")
    daemon_status_p.add_argument("--project", "-p", default=".", help="Project path (default: current directory)")

    # tldr daemon query CMD [--project PATH]
    daemon_query_p = daemon_sub.add_parser("query", help="Send raw JSON command to daemon")
    daemon_query_p.add_argument("cmd", help="Command to send (e.g., ping, status, search)")
    daemon_query_p.add_argument("--project", "-p", default=".", help="Project path (default: current directory)")

    # tldr daemon notify FILE [--project PATH]
    daemon_notify_p = daemon_sub.add_parser("notify", help="Notify daemon of file change (triggers reindex at threshold)")
    daemon_notify_p.add_argument("file", help="Path to changed file")
    daemon_notify_p.add_argument("--project", "-p", default=".", help="Project path (default: current directory)")

    # tldr doctor [--install LANG]
    doctor_p = subparsers.add_parser(
        "doctor", help="Check and install diagnostic tools (type checkers, linters)"
    )
    doctor_p.add_argument(
        "--install", metavar="LANG", help="Install missing tools for language (e.g., python, go)"
    )
    doctor_p.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    # tldrs index [path] - New semantic indexing with Ollama support
    index_p = subparsers.add_parser(
        "index", help="Build semantic index for code search (supports Ollama)"
    )
    index_p.add_argument("path", nargs="?", default=".", help="Project root")
    index_p.add_argument(
        "--backend",
        choices=["auto", "ollama", "sentence-transformers"],
        default="auto",
        help="Embedding backend (auto tries Ollama first)",
    )
    index_p.add_argument(
        "--model",
        default=None,
        help="Embedding model (e.g., nomic-embed-text for Ollama)",
    )
    index_p.add_argument(
        "--summaries",
        action="store_true",
        help="Generate 1-line summaries with local LLM (requires Ollama)",
    )
    index_p.add_argument(
        "--rebuild",
        action="store_true",
        help="Force full rebuild (ignore existing index)",
    )
    index_p.add_argument(
        "--info",
        action="store_true",
        help="Show index info instead of building",
    )

    # tldrs find <query> - Semantic search using the index
    find_p = subparsers.add_parser(
        "find", help="Semantic code search (uses index, run `tldrs index` first)"
    )
    find_p.add_argument("query", help="Natural language query (e.g., 'authentication logic')")
    find_p.add_argument("--path", default=".", help="Project root")
    find_p.add_argument("-k", type=int, default=10, help="Number of results (default: 10)")
    find_p.add_argument(
        "--backend",
        choices=["auto", "ollama", "sentence-transformers"],
        default="auto",
        help="Embedding backend (should match index)",
    )

    # tldrs quickstart - Show agent-focused quick reference
    quickstart_p = subparsers.add_parser(
        "quickstart", help="Show quick reference guide for AI agents"
    )

    # Module subcommands: vhs, wb, bench
    from .modules.vhs import cli as vhs_cli
    from .modules.workbench import cli as wb_cli
    from .modules.bench import cli as bench_cli

    vhs_cli.add_subparser(subparsers)
    wb_cli.add_subparser(subparsers)
    bench_cli.add_subparser(subparsers)

    args = parser.parse_args()

    # Import here to avoid slow startup for --help
    from .modules.core.api import (
        build_project_call_graph,
        extract_file,
        get_cfg_context,
        get_code_structure,
        get_dfg_context,
        get_diff_context,
        get_file_tree,
        get_imports,
        get_relevant_context,
        get_symbol_context_pack,
        get_slice,
        scan_project_files,
        search as api_search,
    )
    from .modules.core.analysis import (
        analyze_architecture,
        analyze_dead_code,
        analyze_impact,
    )
    from .modules.core.dirty_flag import is_dirty, get_dirty_files, clear_dirty
    from .modules.core.patch import patch_call_graph
    from .modules.core.cross_file_calls import ProjectCallGraph

    def _get_or_build_graph(project_path, lang, build_fn):
        """Get cached graph with incremental patches, or build fresh.

        This implements P4 incremental updates:
        1. If no cache exists, do full build
        2. If cache exists but no dirty files, load cache
        3. If cache exists with dirty files, patch incrementally
        """
        import time
        project = Path(project_path).resolve()
        cache_dir = project / ".tldrs" / "cache"
        cache_file = cache_dir / "call_graph.json"

        # Check if we have a cached graph
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
                # Reconstruct graph from cache
                graph = ProjectCallGraph()
                for e in cache_data.get("edges", []):
                    graph.add_edge(e["from_file"], e["from_func"], e["to_file"], e["to_func"])

                # Check for dirty files
                if is_dirty(project):
                    dirty_files = get_dirty_files(project)
                    # Patch incrementally for each dirty file
                    for rel_file in dirty_files:
                        abs_file = project / rel_file
                        if abs_file.exists():
                            graph = patch_call_graph(graph, str(abs_file), str(project), lang=lang)

                    # Update cache with patched graph
                    cache_data = {
                        "edges": [
                            {"from_file": e[0], "from_func": e[1], "to_file": e[2], "to_func": e[3]}
                            for e in graph.edges
                        ],
                        "timestamp": time.time(),
                    }
                    cache_file.write_text(json.dumps(cache_data, indent=2))

                    # Clear dirty flag
                    clear_dirty(project)

                return graph
            except (json.JSONDecodeError, KeyError):
                # Invalid cache, fall through to fresh build
                pass

        # No cache or invalid cache - do fresh build
        graph = build_fn(project_path, language=lang)

        # Save to cache
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "edges": [
                {"from_file": e[0], "from_func": e[1], "to_file": e[2], "to_func": e[3]}
                for e in graph.edges
            ],
            "timestamp": time.time(),
        }
        cache_file.write_text(json.dumps(cache_data, indent=2))

        # Clear any dirty flag since we just rebuilt
        clear_dirty(project)

        return graph

    try:
        if args.command == "tree":
            ext = set(args.ext) if args.ext else None
            result = get_file_tree(
                args.path, extensions=ext, exclude_hidden=not args.show_hidden
            )
            _machine_output(result, args)

        elif args.command == "structure":
            respect_ignore = not getattr(args, "no_ignore", False)
            result = get_code_structure(
                args.path,
                language=args.lang,
                max_results=args.max,
                respect_ignore=respect_ignore,
                respect_gitignore=getattr(args, "respect_gitignore", False),
            )
            _machine_output(result, args)

        elif args.command == "search":
            ext = set(args.ext) if args.ext else None
            respect_ignore = not getattr(args, "no_ignore", False)
            result = api_search(
                args.pattern, args.path,
                extensions=ext,
                context_lines=args.context,
                max_results=args.max,
                max_files=args.max_files,
                respect_ignore=respect_ignore,
                respect_gitignore=getattr(args, "respect_gitignore", False),
            )
            _machine_output(result, args)

        elif args.command == "extract":
            result = extract_file(args.file)

            # Apply filters if specified
            filter_class = getattr(args, "filter_class", None)
            filter_function = getattr(args, "filter_function", None)
            filter_method = getattr(args, "filter_method", None)

            if filter_class or filter_function or filter_method:
                # Filter classes
                if filter_class:
                    result["classes"] = [
                        c for c in result.get("classes", [])
                        if c.get("name") == filter_class
                    ]
                elif filter_method:
                    # Parse Class.method syntax
                    parts = filter_method.split(".", 1)
                    if len(parts) == 2:
                        class_name, method_name = parts
                        filtered_classes = []
                        for c in result.get("classes", []):
                            if c.get("name") == class_name:
                                # Filter to only the requested method
                                c_copy = dict(c)
                                c_copy["methods"] = [
                                    m for m in c.get("methods", [])
                                    if m.get("name") == method_name
                                ]
                                filtered_classes.append(c_copy)
                        result["classes"] = filtered_classes
                else:
                    # No class filter, clear classes
                    result["classes"] = []

                # Filter functions
                if filter_function:
                    result["functions"] = [
                        f for f in result.get("functions", [])
                        if f.get("name") == filter_function
                    ]
                elif not filter_method:
                    # No function filter (and not method filter), clear functions if class filter active
                    if filter_class:
                        result["functions"] = []

            _machine_output(result, args)

        elif args.command == "context":
            project_root = Path(args.project).resolve()

            # Determine if delta mode should be used
            use_delta = False
            session_id = None
            if args.session_id or args.delta:
                if not args.no_delta:
                    use_delta = True
                    store = _get_state_store(project_root)
                    session_id = args.session_id or store.get_or_create_default_session(args.lang)

            # Force ultracompact + json for --machine flag
            fmt = args.format
            if getattr(args, "machine", False):
                fmt = "ultracompact"  # Use ultracompact format, will convert to JSON

            if fmt == "ultracompact":
                from .modules.core.output_formats import format_context_pack

                if use_delta and session_id:
                    pack = _get_context_pack_with_delta(
                        args.project,
                        args.entry,
                        session_id,
                        depth=args.depth,
                        language=args.lang,
                        budget_tokens=args.budget,
                        include_docstrings=args.with_docs,
                    )
                else:
                    pack = get_symbol_context_pack(
                        args.project,
                        args.entry,
                        depth=args.depth,
                        language=args.lang,
                        budget_tokens=args.budget,
                        include_docstrings=args.with_docs,
                    )
                # Use json format for --machine flag
                out_fmt = "json" if getattr(args, "machine", False) else "ultracompact"
                output = format_context_pack(pack, fmt=out_fmt)
            else:
                from .modules.core.output_formats import format_context
                ctx = get_relevant_context(
                    args.project,
                    args.entry,
                    depth=args.depth,
                    language=args.lang,
                    include_docstrings=args.with_docs,
                )
                output = format_context(ctx, fmt=args.format, budget_tokens=args.budget)
            if args.include:
                for ref in args.include:
                    try:
                        included = _vhs_get(ref, project_root)
                    except Exception as exc:
                        print(f"Error: {exc}", file=sys.stderr)
                        sys.exit(1)
                    output += f"\n\n# Included {ref}\n{included.rstrip()}\n"
            if args.max_lines or args.max_bytes:
                from .modules.core.output_formats import truncate_output
                output = truncate_output(output, max_lines=args.max_lines, max_bytes=args.max_bytes)
            if args.output == "vhs":
                try:
                    ref = _vhs_put(output, project_root)
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    sys.exit(1)
                summary = _make_vhs_summary(ctx)
                preview = _make_vhs_preview(output)
                print(_render_vhs_output(ref, summary, preview))
            else:
                print(output)
        elif args.command == "diff-context":
            from .modules.core.output_formats import format_context_pack
            project = Path(args.project).resolve()
            base = args.base or _resolve_diff_base(project)

            # Determine session ID and delta mode
            session_id = args.session_id
            use_delta = not args.no_delta
            if args.delta and not session_id:
                # Auto-generate session ID for --delta flag
                from .modules.core.state_store import StateStore
                store = StateStore(project)
                session_id = store.get_or_create_default_session()

            if use_delta and session_id:
                pack = _get_diff_context_with_delta(
                    project,
                    session_id,
                    base=base,
                    head=args.head,
                    budget_tokens=args.budget,
                    language=args.lang,
                    compress=None if args.compress == "none" else args.compress,
                )
            else:
                pack = get_diff_context(
                    project,
                    base=base,
                    head=args.head,
                    budget_tokens=args.budget,
                    language=args.lang,
                    compress=None if args.compress == "none" else args.compress,
                )
            # Force JSON format when --machine flag is set
            fmt = "json" if getattr(args, "machine", False) else args.format
            diff_output = format_context_pack(pack, fmt=fmt)
            if args.max_lines or args.max_bytes:
                from .modules.core.output_formats import truncate_output
                diff_output = truncate_output(diff_output, max_lines=args.max_lines, max_bytes=args.max_bytes)
            print(diff_output)

        elif args.command == "cfg":
            lang = args.lang or detect_language_from_extension(args.file)
            result = get_cfg_context(args.file, args.function, language=lang)
            _machine_output(result, args)

        elif args.command == "dfg":
            lang = args.lang or detect_language_from_extension(args.file)
            result = get_dfg_context(args.file, args.function, language=lang)
            _machine_output(result, args)

        elif args.command == "slice":
            lang = args.lang or detect_language_from_extension(args.file)
            lines = get_slice(
                args.file,
                args.function,
                args.line,
                direction=args.direction,
                variable=args.var,
                language=lang,
            )
            result = {"lines": sorted(lines), "count": len(lines)}
            if args.max_lines or args.max_bytes:
                from .modules.core.output_formats import truncate_json_output
                indent = None if getattr(args, "machine", False) else 2
                print(truncate_json_output(result, max_lines=args.max_lines, max_bytes=args.max_bytes, indent=indent))
            else:
                _machine_output(result, args)

        elif args.command == "calls":
            # Check for cached graph and dirty files for incremental update
            graph = _get_or_build_graph(args.path, args.lang, build_project_call_graph)
            result = {
                "edges": [
                    {
                        "from_file": e[0],
                        "from_func": e[1],
                        "to_file": e[2],
                        "to_func": e[3],
                    }
                    for e in graph.edges
                ],
                "count": len(graph.edges),
            }
            _machine_output(result, args)

        elif args.command == "impact":
            result = analyze_impact(
                args.path,
                args.func,
                max_depth=args.depth,
                target_file=args.file,
                language=args.lang,
            )
            _machine_output(result, args)

        elif args.command == "dead":
            result = analyze_dead_code(
                args.path,
                entry_points=args.entry if args.entry else None,
                language=args.lang,
            )
            _machine_output(result, args)

        elif args.command == "arch":
            result = analyze_architecture(args.path, language=args.lang)
            _machine_output(result, args)

        elif args.command == "imports":
            file_path = Path(args.file).resolve()
            if not file_path.exists():
                print(f"Error: File not found: {args.file}", file=sys.stderr)
                sys.exit(1)
            lang = args.lang or detect_language_from_extension(args.file)
            result = get_imports(str(file_path), language=lang)
            _machine_output(result, args)

        elif args.command == "importers":
            # Find all files that import the given module
            project = Path(args.path).resolve()
            if not project.exists():
                print(f"Error: Path not found: {args.path}", file=sys.stderr)
                sys.exit(1)

            # Scan all source files and check their imports
            respect_ignore = not getattr(args, 'no_ignore', False)
            respect_gitignore = getattr(args, 'respect_gitignore', False)
            files = scan_project_files(
                str(project),
                language=args.lang,
                respect_ignore=respect_ignore,
                respect_gitignore=respect_gitignore,
            )
            importers = []
            for file_path in files:
                try:
                    imports = get_imports(file_path, language=args.lang)
                    for imp in imports:
                        module = imp.get("module", "")
                        names = imp.get("names", [])
                        # Check if module matches or if any imported name matches
                        if args.module in module or args.module in names:
                            importers.append({
                                "file": str(Path(file_path).relative_to(project)),
                                "import": imp,
                            })
                except Exception:
                    # Skip files that can't be parsed
                    pass

            _machine_output({"module": args.module, "importers": importers}, args)

        elif args.command == "change-impact":
            from .modules.core.change_impact import analyze_change_impact

            result = analyze_change_impact(
                project_path=".",
                files=args.files if args.files else None,
                use_session=args.session,
                use_git=args.git,
                git_base=args.git_base,
                language=args.lang,
                max_depth=args.depth,
            )

            if args.run and result.get("test_command"):
                # Actually run the tests (test_command is a list to avoid shell injection)
                import shlex
                import subprocess as sp
                cmd = result["test_command"]
                print(f"Running: {shlex.join(cmd)}", file=sys.stderr)
                sp.run(cmd)  # No shell=True - safe from injection
            else:
                _machine_output(result, args)

        elif args.command == "diagnostics":
            from .modules.core.diagnostics import (
                get_diagnostics,
                get_project_diagnostics,
                format_diagnostics_for_llm,
            )

            target = Path(args.target).resolve()
            if not target.exists():
                print(f"Error: Target not found: {args.target}", file=sys.stderr)
                sys.exit(1)

            if args.project or target.is_dir():
                result = get_project_diagnostics(
                    str(target),
                    language=args.lang or "python",
                    include_lint=not args.no_lint,
                )
            else:
                result = get_diagnostics(
                    str(target),
                    language=args.lang,
                    include_lint=not args.no_lint,
                )

            if args.format == "text" and not getattr(args, "machine", False):
                print(format_diagnostics_for_llm(result))
            else:
                _machine_output(result, args)

        elif args.command == "warm":
            import os
            import subprocess
            import time

            project_path = Path(args.path).resolve()

            # Validate path exists
            if not project_path.exists():
                print(f"Error: Path not found: {args.path}", file=sys.stderr)
                sys.exit(1)

            if args.background:
                # Spawn background process (cross-platform)
                subprocess.Popen(
                    [sys.executable, "-m", "tldr_swinton.cli", "warm", str(project_path), "--lang", args.lang],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_get_subprocess_detach_kwargs(),
                )
                print(f"Background indexing spawned for {project_path}")
            else:
                # Build call graph
                from .modules.core.cross_file_calls import scan_project

                respect_ignore = not getattr(args, 'no_ignore', False)
                respect_gitignore = getattr(args, 'respect_gitignore', False)
                files = scan_project(
                    project_path,
                    language=args.lang,
                    respect_ignore=respect_ignore,
                    respect_gitignore=respect_gitignore,
                )
                graph = build_project_call_graph(project_path, language=args.lang)

                # Create cache directory
                cache_dir = project_path / ".tldrs" / "cache"
                cache_dir.mkdir(parents=True, exist_ok=True)

                # Save cache file
                cache_file = cache_dir / "call_graph.json"
                cache_data = {
                    "edges": [
                        {"from_file": e[0], "from_func": e[1], "to_file": e[2], "to_func": e[3]}
                        for e in graph.edges
                    ],
                    "timestamp": time.time(),
                }
                cache_file.write_text(json.dumps(cache_data, indent=2))

                # Print stats
                print(f"Indexed {len(files)} files, found {len(graph.edges)} edges")

        elif args.command == "semantic":
            from .modules.semantic.index import build_index, search_index

            if args.action == "index":
                respect_ignore = not getattr(args, 'no_ignore', False)
                respect_gitignore = getattr(args, 'respect_gitignore', False)
                stats = build_index(
                    args.path,
                    language=args.lang,
                    embed_model=args.model,
                    respect_ignore=respect_ignore,
                    respect_gitignore=respect_gitignore,
                )
                print(f"Indexed {stats.total_units} code units")

            elif args.action == "search":
                results = search_index(args.path, args.query, k=args.k, model=args.model)
                print(json.dumps(results, indent=2))

        elif args.command == "doctor":
            import shutil
            import subprocess

            # Tool definitions: language -> (type_checker, linter, install_commands)
            TOOL_INFO = {
                "python": {
                    "type_checker": ("pyright", "pip install pyright  OR  npm install -g pyright"),
                    "linter": ("ruff", "pip install ruff"),
                },
                "typescript": {
                    "type_checker": ("tsc", "npm install -g typescript"),
                    "linter": None,
                },
                "javascript": {
                    "type_checker": None,
                    "linter": ("eslint", "npm install -g eslint"),
                },
                "go": {
                    "type_checker": ("go", "https://go.dev/dl/"),
                    "linter": ("golangci-lint", "brew install golangci-lint  OR  go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest"),
                },
                "rust": {
                    "type_checker": ("cargo", "https://rustup.rs/"),
                    "linter": ("cargo-clippy", "rustup component add clippy"),
                },
                "java": {
                    "type_checker": ("javac", "Install JDK: https://adoptium.net/"),
                    "linter": ("checkstyle", "brew install checkstyle  OR  download from checkstyle.org"),
                },
                "c": {
                    "type_checker": ("gcc", "xcode-select --install  OR  apt install gcc"),
                    "linter": ("cppcheck", "brew install cppcheck  OR  apt install cppcheck"),
                },
                "cpp": {
                    "type_checker": ("g++", "xcode-select --install  OR  apt install g++"),
                    "linter": ("cppcheck", "brew install cppcheck  OR  apt install cppcheck"),
                },
                "ruby": {
                    "type_checker": None,
                    "linter": ("rubocop", "gem install rubocop"),
                },
                "php": {
                    "type_checker": None,
                    "linter": ("phpstan", "composer global require phpstan/phpstan"),
                },
                "kotlin": {
                    "type_checker": ("kotlinc", "brew install kotlin  OR  sdk install kotlin"),
                    "linter": ("ktlint", "brew install ktlint"),
                },
                "swift": {
                    "type_checker": ("swiftc", "xcode-select --install"),
                    "linter": ("swiftlint", "brew install swiftlint"),
                },
                "csharp": {
                    "type_checker": ("dotnet", "https://dotnet.microsoft.com/download"),
                    "linter": None,
                },
                "scala": {
                    "type_checker": ("scalac", "brew install scala  OR  sdk install scala"),
                    "linter": None,
                },
                "elixir": {
                    "type_checker": ("elixir", "brew install elixir  OR  asdf install elixir"),
                    "linter": ("mix", "Included with Elixir"),
                },
                "lua": {
                    "type_checker": None,
                    "linter": ("luacheck", "luarocks install luacheck"),
                },
            }

            # Install commands for --install flag
            INSTALL_COMMANDS = {
                "python": ["pip", "install", "pyright", "ruff"],
                "go": ["go", "install", "github.com/golangci/golangci-lint/cmd/golangci-lint@latest"],
                "rust": ["rustup", "component", "add", "clippy"],
                "ruby": ["gem", "install", "rubocop"],
                "kotlin": ["brew", "install", "kotlin", "ktlint"],
                "swift": ["brew", "install", "swiftlint"],
                "lua": ["luarocks", "install", "luacheck"],
            }

            if args.install:
                lang = args.install.lower()
                if lang not in INSTALL_COMMANDS:
                    print(f"Error: No auto-install available for '{lang}'", file=sys.stderr)
                    print(f"Available: {', '.join(sorted(INSTALL_COMMANDS.keys()))}", file=sys.stderr)
                    sys.exit(1)

                cmd = INSTALL_COMMANDS[lang]
                print(f"Installing tools for {lang}: {' '.join(cmd)}")
                try:
                    subprocess.run(cmd, check=True)
                    print(f"✓ Installed {lang} tools")
                except subprocess.CalledProcessError as e:
                    print(f"✗ Install failed: {e}", file=sys.stderr)
                    sys.exit(1)
                except FileNotFoundError:
                    print(f"✗ Command not found: {cmd[0]}", file=sys.stderr)
                    sys.exit(1)
            else:
                # Check all tools
                results = {}
                for lang, tools in TOOL_INFO.items():
                    lang_result = {"type_checker": None, "linter": None}

                    if tools["type_checker"]:
                        tool_name, install_cmd = tools["type_checker"]
                        path = shutil.which(tool_name)
                        lang_result["type_checker"] = {
                            "name": tool_name,
                            "installed": path is not None,
                            "path": path,
                            "install": install_cmd if not path else None,
                        }

                    if tools["linter"]:
                        tool_name, install_cmd = tools["linter"]
                        path = shutil.which(tool_name)
                        lang_result["linter"] = {
                            "name": tool_name,
                            "installed": path is not None,
                            "path": path,
                            "install": install_cmd if not path else None,
                        }

                    results[lang] = lang_result

                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print("TLDR Diagnostics Check")
                    print("=" * 50)
                    print()

                    missing_count = 0
                    for lang, checks in sorted(results.items()):
                        has_issues = False
                        lines = []

                        tc = checks["type_checker"]
                        if tc:
                            if tc["installed"]:
                                lines.append(f"  ✓ {tc['name']} - {tc['path']}")
                            else:
                                lines.append(f"  ✗ {tc['name']} - not found")
                                lines.append(f"    → {tc['install']}")
                                has_issues = True
                                missing_count += 1

                        linter = checks["linter"]
                        if linter:
                            if linter["installed"]:
                                lines.append(f"  ✓ {linter['name']} - {linter['path']}")
                            else:
                                lines.append(f"  ✗ {linter['name']} - not found")
                                lines.append(f"    → {linter['install']}")
                                has_issues = True
                                missing_count += 1

                        if lines:
                            print(f"{lang.capitalize()}:")
                            for line in lines:
                                print(line)
                            print()

                    if missing_count > 0:
                        print(f"Missing {missing_count} tool(s). Run: tldr doctor --install <lang>")
                    else:
                        print("All diagnostic tools installed!")

        elif args.command == "daemon":
            from .modules.core.daemon import start_daemon, stop_daemon, query_daemon

            project_path = Path(args.project).resolve()

            if args.action == "start":
                # Ensure .tldrs directory exists
                tldr_dir = project_path / ".tldrs"
                tldr_dir.mkdir(parents=True, exist_ok=True)
                # Start daemon (will fork to background on Unix)
                start_daemon(project_path, foreground=False)

            elif args.action == "stop":
                if stop_daemon(project_path):
                    print("Daemon stopped")
                else:
                    print("Daemon not running")

            elif args.action == "status":
                try:
                    result = query_daemon(project_path, {"cmd": "status"})
                    print(f"Status: {result.get('status', 'unknown')}")
                    if 'uptime' in result:
                        uptime = int(result['uptime'])
                        mins, secs = divmod(uptime, 60)
                        hours, mins = divmod(mins, 60)
                        print(f"Uptime: {hours}h {mins}m {secs}s")
                except (ConnectionRefusedError, FileNotFoundError):
                    print("Daemon not running")

            elif args.action == "query":
                try:
                    result = query_daemon(project_path, {"cmd": args.cmd})
                    _machine_output(result, args)
                except (ConnectionRefusedError, FileNotFoundError):
                    if getattr(args, "machine", False):
                        from .modules.core.errors import make_error, ERR_DAEMON
                        print(json.dumps(make_error(ERR_DAEMON, "Daemon not running")))
                    else:
                        print("Error: Daemon not running", file=sys.stderr)
                    sys.exit(1)

            elif args.action == "notify":
                try:
                    file_path = Path(args.file).resolve()
                    result = query_daemon(project_path, {
                        "cmd": "notify",
                        "file": str(file_path)
                    })
                    if result.get("status") == "ok":
                        dirty = result.get("dirty_count", 0)
                        threshold = result.get("threshold", 20)
                        if result.get("reindex_triggered"):
                            print(f"Reindex triggered ({dirty}/{threshold} files)")
                        else:
                            print(f"Tracked: {dirty}/{threshold} files")
                    else:
                        print(f"Error: {result.get('message', 'Unknown error')}", file=sys.stderr)
                        sys.exit(1)
                except (ConnectionRefusedError, FileNotFoundError):
                    # Daemon not running - silently ignore, file edits shouldn't fail
                    pass

        elif args.command == "index":
            from .modules.semantic.index import build_index, search_index, get_index_info

            respect_ignore = not getattr(args, 'no_ignore', False)
            respect_gitignore = getattr(args, 'respect_gitignore', False)

            if args.info:
                # Show index info
                info = get_index_info(args.path)
                if info:
                    print(json.dumps(info, indent=2))
                else:
                    print("No index found. Run `tldrs index .` to create one.")
            else:
                # Build index
                stats = build_index(
                    args.path,
                    backend=args.backend,
                    embed_model=args.model,
                    generate_summaries=args.summaries,
                    rebuild=args.rebuild,
                    respect_ignore=respect_ignore,
                    respect_gitignore=respect_gitignore,
                )
                print(f"\nIndex complete: {stats.total_units} units from {stats.total_files} files")
                if stats.new_units > 0:
                    print(f"  New: {stats.new_units}")
                if stats.updated_units > 0:
                    print(f"  Updated: {stats.updated_units}")
                if stats.unchanged_units > 0:
                    print(f"  Unchanged: {stats.unchanged_units}")

        elif args.command == "find":
            from .modules.semantic.index import search_index

            results = search_index(
                args.path,
                args.query,
                k=args.k,
                backend=args.backend,
            )

            if getattr(args, "machine", False):
                # Machine output - always JSON
                _machine_output({"results": results, "count": len(results)}, args)
            elif not results:
                print("No results found. Make sure you've run `tldrs index` first.")
            else:
                for r in results:
                    score_str = f"[{r['score']:.3f}]"
                    loc = f"{r['file']}:{r['line']}"
                    print(f"{r['rank']:2}. {score_str} {r['name']} ({r['type']})")
                    print(f"      {r['signature']}")
                    print(f"      {loc}")
                    if r.get('summary'):
                        print(f"      → {r['summary']}")
                    print()

        elif args.command == "quickstart":
            # Print the quickstart guide
            quickstart_path = Path(__file__).parent.parent.parent / "docs" / "QUICKSTART.md"
            if quickstart_path.exists():
                print(quickstart_path.read_text())
            else:
                # Fallback inline content if docs not found (e.g., pip install)
                print("""# tldr-swinton Quick Reference for AI Agents

## Decision Tree

What are you trying to do?

1. "Understand recent changes"
   → tldrs diff-context --project . --budget 2000

2. "Find code related to X concept"
   → tldrs find "X concept"

3. "Get context around a function"
   → tldrs context <func> --project . --depth 2 --format ultracompact

4. "See code structure"
   → tldrs structure src/

5. "Edit a file"
   → Read the full file (tldr is for recon, not surgery)

## Essential Commands

# Diff-first context (start here)
tldrs diff-context --project . --budget 2000

# Semantic search (build index first)
tldrs index .
tldrs find "authentication logic"

# Symbol context
tldrs context func_name --project . --depth 2 --format ultracompact

# Structure overview
tldrs structure src/

## Remember

- tldr is for reconnaissance - use it to find and understand code
- Read full files when editing - tldr gives signatures, not full code
- Use --budget to cap tokens - always for large codebases
- Use --format ultracompact - saves tokens

Full guide: https://github.com/mistakeknot/tldr-swinton/blob/main/docs/QUICKSTART.md
""")

        # Module subcommands
        elif args.command == "vhs":
            from .modules.vhs import cli as vhs_cli
            sys.exit(vhs_cli.handle(args))

        elif args.command == "wb":
            from .modules.workbench import cli as wb_cli
            sys.exit(wb_cli.handle(args))

        elif args.command == "bench":
            from .modules.bench import cli as bench_cli
            sys.exit(bench_cli.handle(args))

    except FileNotFoundError as e:
        if getattr(args, "machine", False):
            from .modules.core.errors import make_error, ERR_NOT_FOUND
            print(json.dumps(make_error(ERR_NOT_FOUND, str(e))))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        if getattr(args, "machine", False):
            from .modules.core.errors import make_error, ERR_INTERNAL
            print(json.dumps(make_error(ERR_INTERNAL, str(e))))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if getattr(args, "machine", False):
            from .modules.core.errors import make_error, ERR_INTERNAL
            print(json.dumps(make_error(ERR_INTERNAL, str(e))))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
