"""
TLDR Unified API - Token-efficient code context for LLMs.

Usage:
    from .api import get_relevant_context

    context = get_relevant_context(
        project="/path/to/project",
        entry_point="ClassName.method_name",  # or "function_name"
        depth=2,
        language="python"
    )

    # Returns LLM-ready string with call graph, signatures, complexity
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re

from .ast_extractor import (
    CallGraphInfo,  # Re-exported for API consumers
    ClassInfo,  # Re-exported for API consumers
    FunctionInfo,
    ImportInfo,  # Re-exported for API consumers
    extract_file as _extract_file_impl,
)

# Re-export for public API
__all__ = [
    # Dataclasses from ast_extractor
    "CallGraphInfo",
    "ClassInfo",
    "FunctionInfo",
    "ImportInfo",
    # Main API functions
    "get_relevant_context",
    "get_imports",
    "get_intra_file_calls",
    "extract_file",
    "get_dfg_context",
    "get_pdg_context",
    "get_slice",
    "query",
    # Cross-file functions
    "build_project_call_graph",
    "scan_project_files",
    "build_function_index",
    # Project navigation functions
    "get_file_tree",
    "search",
    "Selection",
    "get_code_structure",
    # P5 #21: Content-hash deduplication
    "ContentHashedIndex",
]
from .cfg_extractor import (
    CFGBlock,  # Re-exported for type hints
    CFGEdge,  # Re-exported for type hints
    CFGInfo,
    extract_c_cfg,
    extract_cpp_cfg,
    extract_csharp_cfg,
    extract_elixir_cfg,
    extract_go_cfg,
    extract_java_cfg,
    extract_kotlin_cfg,
    extract_lua_cfg,
    extract_php_cfg,
    extract_python_cfg,
    extract_ruby_cfg,
    extract_rust_cfg,
    extract_scala_cfg,
    extract_swift_cfg,
    extract_typescript_cfg,
)
from .dedup import ContentHashedIndex  # P5 #21: Content-hash deduplication
from .cross_file_calls import (
    build_project_call_graph,
)
from .cross_file_calls import (
    build_function_index as _build_function_index,
)
from .cross_file_calls import (
    parse_go_imports as _parse_go_imports,
)
from .cross_file_calls import (
    parse_imports as _parse_imports,
)
from .cross_file_calls import (
    parse_rust_imports as _parse_rust_imports,
)
from .cross_file_calls import (
    parse_ts_imports as _parse_ts_imports,
)
from .cross_file_calls import (
    parse_java_imports as _parse_java_imports,
)
from .cross_file_calls import (
    parse_c_imports as _parse_c_imports,
)
from .cross_file_calls import (
    parse_cpp_imports as _parse_cpp_imports,
)
from .cross_file_calls import (
    parse_ruby_imports as _parse_ruby_imports,
)
from .cross_file_calls import (
    parse_kotlin_imports as _parse_kotlin_imports,
)
from .cross_file_calls import (
    parse_scala_imports as _parse_scala_imports,
)
from .cross_file_calls import (
    parse_php_imports as _parse_php_imports,
)
from .cross_file_calls import (
    parse_swift_imports as _parse_swift_imports,
)
from .cross_file_calls import (
    parse_csharp_imports as _parse_csharp_imports,
)
from .cross_file_calls import (
    parse_lua_imports as _parse_lua_imports,
)
from .cross_file_calls import (
    parse_elixir_imports as _parse_elixir_imports,
)
from .cross_file_calls import (
    scan_project as _scan_project,
)
from .dfg_extractor import (
    DFGInfo,
    extract_c_dfg,
    extract_cpp_dfg,
    extract_csharp_dfg,
    extract_elixir_dfg,
    extract_go_dfg,
    extract_java_dfg,
    extract_kotlin_dfg,
    extract_lua_dfg,
    extract_php_dfg,
    extract_python_dfg,
    extract_ruby_dfg,
    extract_rust_dfg,
    extract_scala_dfg,
    extract_swift_dfg,
    extract_typescript_dfg,
)
from .hybrid_extractor import extract_directory  # Re-exported for API
from .workspace import iter_workspace_files
from .pdg_extractor import (
    PDGInfo,
    extract_c_pdg,
    extract_cpp_pdg,
    extract_csharp_pdg,
    extract_go_pdg,
    extract_pdg,
    extract_python_pdg,
    extract_ruby_pdg,
    extract_rust_pdg,
    extract_typescript_pdg,
)

# Explicit exports for public API
__all__ = [
    # Layer 3: CFG types and functions
    "CFGBlock",
    "CFGEdge",
    "get_cfg_context",
    "get_cfg_blocks",
    "get_cfg_edges",
    # Layer 4: DFG functions
    "get_dfg_context",
    # Layer 5: PDG functions
    "get_pdg_context",
    "get_slice",
    # Main API
    "get_relevant_context",
    "get_diff_context",
    "get_symbol_context_pack",
    "query",
    "FunctionContext",
    "RelevantContext",
    # Delta-first extraction (signature-only)
    "SymbolSignature",
    "DiffSymbolSignature",
    "get_signatures_for_entry",
    "get_diff_signatures",
    # Delta-first orchestration
    "get_context_pack_with_delta",
    "get_diff_context_with_delta",
    # Cross-file functions
    "build_project_call_graph",
    "scan_project_files",
    "get_imports",
    "build_function_index",
    "parse_unified_diff",
    "map_hunks_to_symbols",
    "build_diff_context_from_hunks",
    # Security exceptions
    "PathTraversalError",
]


from .engines.symbolkite import (
    FunctionContext,
    RelevantContext,
    SymbolSignature,
    get_relevant_context,
    get_context_pack as _get_symbol_context_pack,
    get_signatures_for_entry as _get_signatures_for_entry,
)
from .engines.difflens import (
    DiffSymbolSignature,
    get_diff_signatures as _get_diff_signatures,
)
from .engines.delta import (
    get_context_pack_with_delta,
    get_diff_context_with_delta,
)
from .zoom import ZoomLevel
from .path_utils import PathTraversalError, _resolve_source, _validate_path_containment


@dataclass
class FunctionContext:
    """Context for a single function."""
    name: str
    file: str
    line: int
    signature: str
    docstring: str | None = None
    calls: list[str] = field(default_factory=list)
    depth: int = 0
    blocks: int | None = None  # CFG blocks count
    cyclomatic: int | None = None  # Cyclomatic complexity


@dataclass
class RelevantContext:
    """The full context returned by get_relevant_context."""
    entry_point: str
    depth: int
    functions: list[FunctionContext] = field(default_factory=list)

    def to_llm_string(self) -> str:
        """Format for LLM injection."""
        lines = [
            f"## Code Context: {self.entry_point} (depth={self.depth})",
            ""
        ]

        for func in self.functions:
            # Indentation based on call depth
            indent = "  " * min(func.depth, self.depth)

            # Function header
            short_file = Path(func.file).name if func.file else "?"
            lines.append(f"{indent}📍 {func.name} ({short_file}:{func.line})")
            lines.append(f"{indent}   {func.signature}")

            # Docstring (truncated)
            if func.docstring:
                doc = func.docstring.split('\n')[0][:80]
                lines.append(f"{indent}   # {doc}")

            # Complexity
            if func.blocks is not None:
                complexity_marker = "🔥" if func.cyclomatic and func.cyclomatic > 10 else ""
                lines.append(f"{indent}   ⚡ complexity: {func.cyclomatic or '?'} ({func.blocks} blocks) {complexity_marker}")

            # Calls
            if func.calls:
                calls_str = ", ".join(func.calls[:5])
                if len(func.calls) > 5:
                    calls_str += f" (+{len(func.calls)-5} more)"
                lines.append(f"{indent}   → calls: {calls_str}")

            lines.append("")

        # Footer with stats
        result = "\n".join(lines)
        token_estimate = len(result) // 4
        return result + f"\n---\n📊 {len(self.functions)} functions | ~{token_estimate} tokens"


def parse_unified_diff(diff_text: str) -> list[tuple[str, int, int]]:
    from .engines.difflens import parse_unified_diff as _parse_unified_diff

    return _parse_unified_diff(diff_text)


def map_hunks_to_symbols(
    project: str | Path,
    hunks: list[tuple[str, int, int]],
    language: str = "python",
    _project_index: "ProjectIndex | None" = None,
) -> dict[str, set[int]]:
    from .engines.difflens import map_hunks_to_symbols as _map_hunks_to_symbols

    return _map_hunks_to_symbols(project, hunks, language=language, _project_index=_project_index)


def build_diff_context_from_hunks(
    project: str | Path,
    hunks: list[tuple[str, int, int]],
    language: str = "python",
    budget_tokens: int | None = None,
    compress: str | None = None,
    zoom_level: ZoomLevel = ZoomLevel.L4,
    strip_comments: bool = False,
    compress_imports: bool = False,
    type_prune: bool = False,
    _project_index: "ProjectIndex | None" = None,
) -> dict:
    from .engines.difflens import (
        build_diff_context_from_hunks as _build_diff_context_from_hunks,
    )

    return _build_diff_context_from_hunks(
        project,
        hunks,
        language=language,
        budget_tokens=budget_tokens,
        compress=compress,
        zoom_level=zoom_level,
        strip_comments=strip_comments,
        compress_imports=compress_imports,
        type_prune=type_prune,
        _project_index=_project_index,
    )


def get_diff_context(
    project: str | Path,
    base: str | None = None,
    head: str | None = None,
    budget_tokens: int | None = None,
    language: str = "python",
    compress: str | None = None,
    zoom_level: ZoomLevel = ZoomLevel.L4,
    strip_comments: bool = False,
    compress_imports: bool = False,
    type_prune: bool = False,
    _project_index: "ProjectIndex | None" = None,
) -> dict:
    from .engines.difflens import get_diff_context as _get_diff_context

    return _get_diff_context(
        project,
        base=base,
        head=head,
        budget_tokens=budget_tokens,
        language=language,
        compress=compress,
        zoom_level=zoom_level,
        strip_comments=strip_comments,
        compress_imports=compress_imports,
        type_prune=type_prune,
        _project_index=_project_index,
    )


def get_dfg_context(
    source_or_path: str,
    function_name: str,
    language: str = "python"
) -> dict:
    from .engines.dfg import get_dfg_context as _get_dfg_context

    return _get_dfg_context(
        source_or_path,
        function_name,
        language=language,
    )


# =============================================================================
# CFG API Functions (Layer 3)
# =============================================================================


def get_cfg_context(
    source_or_path: str,
    function_name: str,
    language: str = "python"
) -> dict:
    from .engines.cfg import get_cfg_context as _get_cfg_context

    return _get_cfg_context(
        source_or_path,
        function_name,
        language=language,
    )


def get_cfg_blocks(
    source_or_path: str,
    function_name: str,
    language: str = "python"
) -> list[dict]:
    """
    Get CFG basic blocks for a function.

    Basic blocks are sequences of statements with no internal branches.
    Control enters only at the first statement and leaves only at the last.

    Args:
        source_or_path: Source code string OR path to file (auto-detected)
        function_name: Name of function to analyze
        language: python, typescript, go, or rust (defaults to python)

    Returns:
        List of block dicts, each containing:
          - id: block identifier
          - type: block type (entry, branch, loop_header, return, exit, body)
          - lines: [start_line, end_line]
          - calls: list of function calls in this block (if any)

        Returns empty list if function not found.
    """
    cfg = get_cfg_context(source_or_path, function_name, language)
    return cfg.get("blocks", [])


def get_cfg_edges(
    source_or_path: str,
    function_name: str,
    language: str = "python"
) -> list[dict]:
    """
    Get CFG control flow edges for a function.

    Edges represent possible control flow transitions between basic blocks.

    Args:
        source_or_path: Source code string OR path to file (auto-detected)
        function_name: Name of function to analyze
        language: python, typescript, go, or rust (defaults to python)

    Returns:
        List of edge dicts, each containing:
          - from: source block ID
          - to: target block ID
          - type: edge type (true, false, unconditional, back_edge, break, continue)
          - condition: human-readable condition (for conditional edges)

        Returns empty list if function not found.
    """
    cfg = get_cfg_context(source_or_path, function_name, language)
    return cfg.get("edges", [])


def query(
    project: str | Path,
    query: str,
    depth: int = 2,
    language: str = "python"
) -> str:
    """
    Convenience function that returns LLM-ready string directly.

    Args:
        project: Path to project root
        query: Function or method name to start from
        depth: Call graph traversal depth
        language: Programming language

    Returns:
        Formatted string ready for LLM context injection
    """
    ctx = get_relevant_context(project, query, depth, language)
    return ctx.to_llm_string()


# =============================================================================
# PDG API Functions (Layer 5)
# =============================================================================

def get_pdg_context(
    source_or_path: str,
    function_name: str,
    language: str = "python"
) -> dict | None:
    from .engines.pdg import get_pdg_context as _get_pdg_context

    return _get_pdg_context(
        source_or_path,
        function_name,
        language=language,
    )


def get_slice(
    source_or_path: str,
    function_name: str,
    line: int,
    direction: str = "backward",
    variable: str | None = None,
    language: str = "python"
) -> set[int]:
    from .engines.slice import get_slice as _get_slice

    return _get_slice(
        source_or_path,
        function_name,
        line,
        direction=direction,
        variable=variable,
        language=language,
    )


# ==============================================================================
# Layer 2: Cross-File Call Graph Functions
# ==============================================================================


def scan_project_files(
    root: str,
    language: str = "python",
    respect_ignore: bool = True,
    respect_gitignore: bool = False,
) -> list[str]:
    """
    Find all source files in project for given language.

    Args:
        root: Project root directory path
        language: "python", "typescript", "go", or "rust"
        respect_ignore: If True, respect .tldrsignore patterns (default True)
        respect_gitignore: If True, also respect .gitignore patterns (default False)

    Returns:
        List of absolute paths to source files

    Example:
        >>> files = scan_project_files("/path/to/project", "python")
        >>> print(files)
        ['/path/to/project/main.py', '/path/to/project/utils/helper.py']
    """
    return _scan_project(
        root,
        language,
        respect_ignore=respect_ignore,
        respect_gitignore=respect_gitignore,
    )


def get_imports(file_path: str, language: str = "python") -> list[dict]:
    """
    Parse imports from a source file.

    Args:
        file_path: Path to source file
        language: "python", "typescript", "go", or "rust"

    Returns:
        List of import info dicts. Structure varies by language:
        - Python: {module, names, is_from, alias/aliases}
        - TypeScript: {module, names, is_default, aliases}
        - Go: {module, alias}
        - Rust: {module, names, is_mod}

    Example:
        >>> imports = get_imports("/path/to/file.py", "python")
        >>> print(imports)
        [{'module': 'os', 'names': [], 'is_from': False, 'alias': None},
         {'module': 'pathlib', 'names': ['Path'], 'is_from': True, 'aliases': {}}]
    """
    if language == "python":
        return _parse_imports(file_path)
    elif language == "typescript" or language == "javascript":
        return _parse_ts_imports(file_path)
    elif language == "go":
        return _parse_go_imports(file_path)
    elif language == "rust":
        return _parse_rust_imports(file_path)
    elif language == "java":
        return _parse_java_imports(file_path)
    elif language == "c":
        return _parse_c_imports(file_path)
    elif language == "cpp":
        return _parse_cpp_imports(file_path)
    elif language == "ruby":
        return _parse_ruby_imports(file_path)
    elif language == "php":
        return _parse_php_imports(file_path)
    elif language == "kotlin":
        return _parse_kotlin_imports(file_path)
    elif language == "swift":
        return _parse_swift_imports(file_path)
    elif language == "csharp":
        return _parse_csharp_imports(file_path)
    elif language == "scala":
        return _parse_scala_imports(file_path)
    elif language == "lua":
        return _parse_lua_imports(file_path)
    elif language == "elixir":
        return _parse_elixir_imports(file_path)
    else:
        raise ValueError(f"Unsupported language: {language}")


def build_function_index(root: str, language: str = "python") -> dict:
    """
    Build index mapping (module, func) -> file_path for all functions.

    Args:
        root: Project root directory path
        language: "python", "typescript", "go", or "rust"

    Returns:
        Dict mapping (module_name, func_name) tuples and "module.func" strings
        to relative file paths

    Example:
        >>> index = build_function_index("/path/to/project", "python")
        >>> print(index[("utils", "helper")])
        'utils.py'
        >>> print(index["utils.helper"])
        'utils.py'
    """
    return _build_function_index(root, language)


# =============================================================================
# Layer 1 (AST) API Functions
# =============================================================================


def get_intra_file_calls(file_path: str) -> dict:
    """
    Get call graph within a single file.

    Extracts function call relationships showing which functions
    call which other functions within the same file.

    Args:
        file_path: Path to the file to analyze

    Returns:
        Dict with two keys:
        - calls: dict mapping caller -> list of callees
        - called_by: dict mapping callee -> list of callers

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file cannot be parsed

    Example:
        >>> cg = get_intra_file_calls("/path/to/file.py")
        >>> cg["calls"]["main"]  # Functions called by main
        ['helper', 'process']
        >>> cg["called_by"]["helper"]  # Functions that call helper
        ['main']
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    module_info = _extract_file_impl(file_path)
    return {
        "calls": dict(module_info.call_graph.calls),
        "called_by": dict(module_info.call_graph.called_by),
    }


def extract_file(file_path: str, base_path: str | None = None) -> dict:
    """
    Extract code structure from any supported file.

    Generic file extractor that returns complete module information
    including imports, functions, classes, and call graph.

    Args:
        file_path: Path to the file to analyze
        base_path: Optional base directory for path containment validation.
                   If provided, file_path must resolve within base_path.

    Returns:
        Dict containing:
        - file_path: Path to the analyzed file
        - language: Detected language (e.g., "python")
        - docstring: Module-level docstring if present
        - imports: List of import dicts
        - functions: List of function dicts with signatures
        - classes: List of class dicts with methods
        - call_graph: Dict with calls and called_by relationships

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file type is not supported or path is invalid
        PathTraversalError: If path escapes base_path via traversal

    Example:
        >>> info = extract_file("/path/to/module.py")
        >>> print(info["functions"][0]["signature"])
        'def my_function(x: int) -> str'
    """
    # Security: Validate path containment
    _validate_path_containment(file_path, base_path)

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    module_info = _extract_file_impl(file_path)
    return module_info.to_dict()


# =============================================================================
# Project Navigation Functions
# =============================================================================


def get_file_tree(
    root: str | Path,
    extensions: set[str] | None = None,
    exclude_hidden: bool = True,
) -> dict:
    """
    Get file tree structure for a project.

    Args:
        root: Root directory to scan
        extensions: Optional set of extensions to include (e.g., {".py", ".ts"})
        exclude_hidden: If True, exclude hidden files/directories (default True)

    Returns:
        Dict with tree structure:
        {
            "name": "project",
            "type": "dir",
            "children": [
                {"name": "src", "type": "dir", "children": [...]},
                {"name": "main.py", "type": "file", "path": "src/main.py"}
            ]
        }

    Raises:
        PathTraversalError: If root path contains directory traversal patterns
    """
    # Security: Validate path containment
    _validate_path_containment(str(root))

    root = Path(root)

    def scan_dir(path: Path) -> dict:
        result = {"name": path.name, "type": "dir", "children": []}

        try:
            items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            return result

        for item in items:
            # Skip hidden files/dirs
            if exclude_hidden and item.name.startswith("."):
                continue

            if item.is_dir():
                child = scan_dir(item)
                # Only include non-empty directories
                if child["children"] or extensions is None:
                    result["children"].append(child)
            elif item.is_file():
                if extensions is None or item.suffix in extensions:
                    result["children"].append(
                        {
                            "name": item.name,
                            "type": "file",
                            "path": str(item.relative_to(root)),
                        }
                    )

        return result

    return scan_dir(root)


def search(
    pattern: str,
    root: str | Path,
    extensions: set[str] | None = None,
    context_lines: int = 0,
    max_results: int = 100,
    max_files: int = 10000,
    respect_gitignore: bool = False,
    respect_ignore: bool = True,
) -> list[dict]:
    """
    Search files for a regex pattern.

    Args:
        pattern: Regex pattern to search for
        root: Root directory to search in
        extensions: Optional set of extensions to filter (e.g., {".py"})
        context_lines: Number of context lines to include (default 0)
        max_results: Maximum matches to return (default 100, 0 = unlimited)
        max_files: Maximum files to scan (default 10000, 0 = unlimited)
        respect_gitignore: If True, respect .gitignore patterns (default False)
        respect_ignore: If True, respect .tldrsignore patterns (default True)

    Returns:
        List of matches:
        [
            {"file": "src/main.py", "line": 10, "content": "def hello():"},
            ...
        ]

    Raises:
        PathTraversalError: If root path contains directory traversal patterns
    """
    # Security: Validate path containment
    _validate_path_containment(str(root))

    import re

    results = []
    root = Path(root)
    compiled = re.compile(pattern)
    files_scanned = 0

    for file_path in iter_workspace_files(
        root,
        extensions=extensions,
        respect_ignore=respect_ignore,
        respect_gitignore=respect_gitignore,
    ):
        # Check file limit
        if max_files > 0 and files_scanned >= max_files:
            break

        files_scanned += 1
        try:
            rel_path = file_path.relative_to(root)
        except ValueError:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()

            for i, line in enumerate(lines, 1):
                if compiled.search(line):
                    match = {
                        "file": str(file_path.relative_to(root)),
                        "line": i,
                        "content": line.strip(),
                    }

                    # Add context if requested
                    if context_lines > 0:
                        start = max(0, i - 1 - context_lines)
                        end = min(len(lines), i + context_lines)
                        match["context"] = lines[start:end]

                    results.append(match)

                    # Check result limit
                    if max_results > 0 and len(results) >= max_results:
                        return results
        except (OSError, UnicodeDecodeError):
            pass

    return results


class Selection:
    """
    Manage file selection state for batch operations.

    Usage:
        sel = Selection()
        sel.add("src/main.py", "src/utils.py")
        sel.remove("src/utils.py")

        for f in sel.files:
            info = extract_file(f)
    """

    def __init__(self):
        self._selected: set[str] = set()

    def add(self, *paths: str) -> "Selection":
        """Add paths to selection."""
        self._selected.update(paths)
        return self

    def remove(self, *paths: str) -> "Selection":
        """Remove paths from selection."""
        self._selected -= set(paths)
        return self

    def clear(self) -> "Selection":
        """Clear all selection."""
        self._selected.clear()
        return self

    def set(self, *paths: str) -> "Selection":
        """Replace entire selection with new paths."""
        self._selected = set(paths)
        return self

    @property
    def files(self) -> list[str]:
        """Return selected files as sorted list."""
        return sorted(self._selected)

    def __contains__(self, path: str) -> bool:
        """Check if path is selected."""
        return path in self._selected

    def __len__(self) -> int:
        """Return number of selected files."""
        return len(self._selected)


def get_code_structure(
    root: str | Path,
    language: str = "python",
    max_results: int = 100,
    respect_gitignore: bool = False,
    respect_ignore: bool = True,
) -> dict:
    """
    Get code structure (codemaps) for all files in a project.

    Args:
        root: Root directory to analyze
        language: Language to analyze ("python", "typescript", "go", "rust")
        max_results: Maximum number of files to analyze (default 100)
        respect_gitignore: If True, respect .gitignore patterns (default False)
        respect_ignore: If True, respect .tldrsignore patterns (default True)

    Returns:
        Dict with codemap structure:
        {
            "root": "/path/to/project",
            "files": [
                {
                    "path": "src/main.py",
                    "functions": ["main", "helper"],
                    "classes": ["MyClass"],
                    "imports": ["os", "sys"]
                },
                ...
            ]
        }
    """
    root = Path(root)

    # Get extension map for language
    ext_map = {
        "python": {".py"},
        "typescript": {".ts", ".tsx"},
        "javascript": {".js", ".jsx"},
        "go": {".go"},
        "rust": {".rs"},
        "java": {".java"},
        "c": {".c", ".h"},
        "cpp": {".cpp", ".cc", ".cxx", ".hpp"},
        "swift": {".swift"},
        "kotlin": {".kt", ".kts"},
        "scala": {".scala"},
        "ruby": {".rb"},
        "php": {".php"},
        "csharp": {".cs"},
        "elixir": {".ex", ".exs"},
        "lua": {".lua"},
    }

    extensions = ext_map.get(language, {".py"})

    # Handle single file case - auto-detect language from extension
    if root.is_file():
        # Detect language from file extension
        ext_to_lang = {
            ".py": "python",
            ".ts": "typescript", ".tsx": "typescript",
            ".js": "javascript", ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c", ".h": "c",
            ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
            ".swift": "swift",
            ".kt": "kotlin", ".kts": "kotlin",
            ".scala": "scala",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
            ".ex": "elixir", ".exs": "elixir",
            ".lua": "lua",
        }
        detected_lang = ext_to_lang.get(root.suffix.lower(), language)
        result = {"root": str(root), "language": detected_lang, "files": []}

        try:
            info = _extract_file_impl(str(root))
            info_dict = info.to_dict()
            file_entry = {
                "path": root.name,
                "functions": [f["name"] for f in info_dict.get("functions", [])],
                "classes": [c["name"] for c in info_dict.get("classes", [])],
                "imports": info_dict.get("imports", []),
            }
            result["files"].append(file_entry)
        except Exception:
            pass
        return result

    result = {"root": str(root), "language": language, "files": []}

    count = 0
    for file_path in iter_workspace_files(
        root,
        extensions=extensions,
        respect_ignore=respect_ignore,
        respect_gitignore=respect_gitignore,
    ):
        if count >= max_results:
            break

        try:
            info = _extract_file_impl(str(file_path))
            info_dict = info.to_dict()

            file_entry = {
                "path": str(file_path.relative_to(root)),
                "functions": [f["name"] for f in info_dict.get("functions", [])],
                "classes": [c["name"] for c in info_dict.get("classes", [])],
                "imports": info_dict.get("imports", []),
            }

            result["files"].append(file_entry)
            count += 1
        except Exception:
            # Skip files that can't be parsed
            pass

    return result


def get_symbol_context_pack(
    project: str | Path,
    entry_point: str,
    depth: int = 2,
    language: str = "python",
    budget_tokens: int | None = None,
    include_docstrings: bool = False,
    etag: str | None = None,
    zoom_level: ZoomLevel = ZoomLevel.L4,
    strip_comments: bool = False,
    compress_imports: bool = False,
    type_prune: bool = False,
    _project_index: "ProjectIndex | None" = None,
) -> dict:
    return _get_symbol_context_pack(
        project,
        entry_point,
        depth=depth,
        language=language,
        budget_tokens=budget_tokens,
        include_docstrings=include_docstrings,
        etag=etag,
        zoom_level=zoom_level,
        strip_comments=strip_comments,
        compress_imports=compress_imports,
        type_prune=type_prune,
        _project_index=_project_index,
    )


def get_signatures_for_entry(
    project: str | Path,
    entry_point: str,
    depth: int = 2,
    language: str = "python",
    disambiguate: bool = True,
    type_prune: bool = False,
    _project_index: "ProjectIndex | None" = None,
) -> list[SymbolSignature] | dict:
    """Get symbol signatures without extracting code bodies.

    This is the foundation of delta-first extraction. By getting only signatures,
    we can compute ETags and check delta BEFORE extracting code, avoiding wasted
    work for unchanged symbols.

    Args:
        project: Path to project root
        entry_point: Function or method name to start from
        depth: Call graph traversal depth (default 2)
        language: Programming language (default "python")
        disambiguate: If True, auto-select best match for ambiguous entries

    Returns:
        List of SymbolSignature objects, or error dict if ambiguous and not disambiguate

    Example:
        >>> sigs = get_signatures_for_entry("/project", "main", depth=2)
        >>> for sig in sigs:
        ...     print(f"{sig.symbol_id}: {sig.signature}")
    """
    return _get_signatures_for_entry(
        project,
        entry_point,
        depth=depth,
        language=language,
        disambiguate=disambiguate,
        type_prune=type_prune,
        _project_index=_project_index,
    )


def get_diff_signatures(
    project: str | Path,
    hunks: list[tuple[str, int, int]],
    language: str = "python",
    type_prune: bool = False,
    _project_index: "ProjectIndex | None" = None,
) -> list[DiffSymbolSignature]:
    """Get signatures for symbols affected by diff hunks without extracting code.

    This is the foundation of delta-first diff context. By getting only signatures,
    we can compute ETags and check delta BEFORE extracting code, avoiding wasted
    work for unchanged symbols.

    Args:
        project: Path to project root
        hunks: List of (file_path, start_line, end_line) from parse_unified_diff
        language: Programming language

    Returns:
        List of DiffSymbolSignature objects

    Example:
        >>> diff_text = subprocess.run(["git", "diff"], capture_output=True, text=True).stdout
        >>> hunks = parse_unified_diff(diff_text)
        >>> sigs = get_diff_signatures("/project", hunks)
        >>> for sig in sigs:
        ...     print(f"{sig.symbol_id}: {sig.relevance_label}")
    """
    return _get_diff_signatures(project, hunks, language=language, type_prune=type_prune, _project_index=_project_index)


# CLI entry point
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m tldr_swinton.api <project_path> <entry_point> [depth] [language]")
        print("Example: python -m tldr_swinton.api /path/to/project build_project_call_graph 2 python")
        sys.exit(1)

    project_path = sys.argv[1]
    entry = sys.argv[2]
    depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    lang = sys.argv[4] if len(sys.argv) > 4 else "python"

    print(query(project_path, entry, depth, lang))
