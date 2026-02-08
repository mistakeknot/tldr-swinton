"""Structural code search using ast-grep (tree-sitter CST patterns).

ast-grep enables pattern-based code matching using tree-sitter concrete syntax trees.
Patterns use meta-variables: $VAR matches single nodes, $$$ARGS matches multiple nodes.

Examples:
    "def $FUNC($$$ARGS): $$$BODY return None"  - functions that return None
    "if $COND: $$$BODY"                         - all if statements
    "$OBJ.$METHOD($$$ARGS)"                     - all method calls

Included in base install (ast-grep-py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..contextpack_engine import Candidate
from ..workspace import iter_workspace_files

logger = logging.getLogger(__name__)

# Language mapping from file extension to ast-grep language name
_EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".lua": "lua",
}


@dataclass
class StructuralMatch:
    """A single structural match from ast-grep."""

    file: str
    line: int
    end_line: int
    text: str
    meta_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class StructuralSearchResult:
    """Results from a structural search."""

    pattern: str
    language: str | None
    matches: list[StructuralMatch] = field(default_factory=list)


def _check_astgrep() -> bool:
    """Check if ast-grep-py is available."""
    try:
        import ast_grep_py  # noqa: F401

        return True
    except ImportError:
        return False


def get_structural_search(
    project_path: str,
    pattern: str,
    language: str | None = None,
    budget_tokens: int | None = None,
    max_results: int = 50,
) -> StructuralSearchResult:
    """Search for structural patterns in code using ast-grep.

    Args:
        project_path: Root directory to search
        pattern: ast-grep pattern with meta-variables ($VAR, $$$ARGS)
        language: Language to search (auto-detected from extensions if None)
        budget_tokens: Optional token budget to limit results
        max_results: Maximum number of matches to return

    Returns:
        StructuralSearchResult with all matches

    Raises:
        ImportError: If ast-grep-py is not installed
    """
    try:
        from ast_grep_py import SgRoot
    except ImportError:
        raise ImportError(
            "ast-grep-py is required for structural search. "
            "Reinstall with: uv tool install --force tldr-swinton"
        )

    root = Path(project_path).resolve()
    result = StructuralSearchResult(pattern=pattern, language=language)
    token_count = 0

    # Determine which extensions to scan
    if language:
        target_exts = {ext for ext, lang in _EXT_TO_LANG.items() if lang == language}
    else:
        target_exts = set(_EXT_TO_LANG.keys())

    for file_path in iter_workspace_files(root):
        ext = file_path.suffix
        if ext not in target_exts:
            continue

        file_lang = _EXT_TO_LANG.get(ext)
        if not file_lang:
            continue

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        try:
            sg = SgRoot(source, file_lang)
            root_node = sg.root()
            matches = root_node.find_all(pattern=pattern)
        except Exception as e:
            logger.debug("ast-grep failed on %s: %s", file_path, e)
            continue

        for match in matches:
            match_range = match.range()
            match_text = match.text()

            # Extract meta-variable bindings
            meta_vars = {}
            try:
                env = match.get_env()
                for key in env.keys():
                    node = env.get(key)
                    if node:
                        meta_vars[key] = node.text()
            except Exception:
                pass  # meta-var extraction is best-effort

            rel_path = str(file_path.relative_to(root))
            sm = StructuralMatch(
                file=rel_path,
                line=match_range.start.line + 1,  # 0-indexed to 1-indexed
                end_line=match_range.end.line + 1,
                text=match_text,
                meta_vars=meta_vars,
            )
            result.matches.append(sm)

            # Budget tracking
            if budget_tokens is not None:
                token_count += len(match_text) // 4
                if token_count >= budget_tokens:
                    return result

            if len(result.matches) >= max_results:
                return result

    return result


def structural_matches_to_candidates(
    matches: list[StructuralMatch],
) -> list[Candidate]:
    """Convert structural matches to Candidate objects for ContextPack pipeline."""
    candidates = []
    for i, match in enumerate(matches):
        symbol_id = f"{match.file}:{match.line}"
        candidates.append(
            Candidate(
                symbol_id=symbol_id,
                relevance=10,
                relevance_label="structural-match",
                order=i,
                signature=f"{match.file}:{match.line}",
                code=match.text,
                lines=(match.line, match.end_line),
            )
        )
    return candidates
