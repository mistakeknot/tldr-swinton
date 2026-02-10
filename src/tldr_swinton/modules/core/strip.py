"""AST-aware comment and docstring stripping via tree-sitter."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


@dataclass
class StripConfig:
    strip_inline_comments: bool = True
    strip_block_comments: bool = True
    truncate_docstrings: bool = True  # keep first line only
    strip_type_comments: bool = True  # # type: ignore, etc.
    preserve_markers: set[str] = field(
        default_factory=lambda: {"TODO", "FIXME", "HACK", "XXX", "NOTE", "WARN"}
    )


_PARSER_CACHE: dict[str, Any] = {}
_TYPE_COMMENT_RE = re.compile(r"#\s*type\s*:", re.IGNORECASE)
_LANGUAGE_ALIASES = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "javascript": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "typescript": "typescript",
    "go": "go",
    "golang": "go",
    "rs": "rust",
    "rust": "rust",
}


def _normalize_language(language: str) -> str:
    return _LANGUAGE_ALIASES.get((language or "").lower(), (language or "").lower())


def _load_tree_sitter_language(language: str) -> Any | None:
    try:
        from tree_sitter import Language
    except Exception:
        return None

    try:
        if language == "python":
            import tree_sitter_python

            return Language(tree_sitter_python.language())
        if language == "javascript":
            import tree_sitter_javascript

            return Language(tree_sitter_javascript.language())
        if language == "typescript":
            import tree_sitter_typescript

            return Language(tree_sitter_typescript.language_typescript())
        if language == "go":
            import tree_sitter_go

            return Language(tree_sitter_go.language())
        if language == "rust":
            import tree_sitter_rust

            return Language(tree_sitter_rust.language())
    except Exception:
        return None
    return None


def _get_parser(language: str) -> Any | None:
    language = _normalize_language(language)
    parser = _PARSER_CACHE.get(language)
    if parser is not None:
        return parser

    lang = _load_tree_sitter_language(language)
    if lang is None:
        return None

    try:
        from tree_sitter import Parser
    except Exception:
        return None

    try:
        parser = Parser()
        parser.language = lang
    except Exception:
        try:
            parser = Parser(lang)
        except Exception:
            return None
    _PARSER_CACHE[language] = parser
    return parser


def _contains_marker(text: str, markers: set[str]) -> bool:
    upper_text = text.upper()
    return any(marker.upper() in upper_text for marker in markers)


def _blank_preserving_lines(text: str) -> str:
    if not text:
        return text
    return "\n" * text.count("\n")


def _truncate_preserving_lines(text: str) -> str:
    if not text:
        return text
    parts = text.split("\n")
    if len(parts) <= 1:
        return text
    return parts[0] + ("\n" * (len(parts) - 1))


def _is_comment_node(node: Any, language: str) -> bool:
    node_type = node.type
    if language == "rust":
        return node_type in {"line_comment", "block_comment"}
    return node_type == "comment"


def _is_docstring_node(node: Any) -> bool:
    if node.type != "expression_statement":
        return False
    if not getattr(node, "named_children", None):
        return False

    first_child = node.named_children[0]
    if first_child.type not in {"string", "concatenated_string"}:
        return False

    parent = node.parent
    if parent is None:
        return False

    if parent.type == "module":
        pass
    elif parent.type == "block":
        owner = parent.parent
        if owner is None or owner.type not in {
            "function_definition",
            "async_function_definition",
            "class_definition",
            "decorated_definition",
        }:
            return False
    else:
        return False

    named_children = getattr(parent, "named_children", [])
    if not named_children:
        return False
    first_stmt = named_children[0]
    return first_stmt.start_byte == node.start_byte and first_stmt.end_byte == node.end_byte


def _should_strip_comment(
    text: str,
    node_type: str,
    language: str,
    config: StripConfig,
) -> bool:
    if _contains_marker(text, config.preserve_markers):
        return False

    if language == "python" and config.strip_type_comments and _TYPE_COMMENT_RE.search(text):
        return True

    is_block = node_type == "block_comment" or text.lstrip().startswith("/*")
    if is_block:
        return config.strip_block_comments
    return config.strip_inline_comments


def _collect_replacements(source: str, language: str, config: StripConfig) -> list[tuple[int, int, str]]:
    parser = _get_parser(language)
    if parser is None:
        return []

    source_bytes = source.encode("utf-8")
    try:
        tree = parser.parse(source_bytes)
    except Exception:
        return []

    replacements: list[tuple[int, int, str]] = []
    normalized_language = _normalize_language(language)
    stack = [tree.root_node]

    while stack:
        node = stack.pop()
        node_type = node.type
        start = node.start_byte
        end = node.end_byte
        if end > start:
            text = source_bytes[start:end].decode("utf-8", errors="replace")
            if _is_comment_node(node, normalized_language):
                if _should_strip_comment(text, node_type, normalized_language, config):
                    replacements.append((start, end, _blank_preserving_lines(text)))
            elif (
                normalized_language == "python"
                and config.truncate_docstrings
                and _is_docstring_node(node)
                and not _contains_marker(text, config.preserve_markers)
            ):
                replacements.append((start, end, _truncate_preserving_lines(text)))
        for child in reversed(node.children):
            stack.append(child)

    if not replacements:
        return []

    # Remove overlaps while keeping the earliest enclosing span.
    replacements.sort(key=lambda item: (item[0], item[1]))
    merged: list[tuple[int, int, str]] = []
    for item in replacements:
        if merged and item[0] < merged[-1][1]:
            continue
        merged.append(item)
    return merged


def strip_code(source: str, language: str, config: StripConfig | None = None) -> str:
    """Strip comments/docstrings while preserving line count for alignment."""
    if not source:
        return source

    cfg = config or StripConfig()
    replacements = _collect_replacements(source, language, cfg)
    if not replacements:
        return source

    out = source
    for start, end, replacement in sorted(replacements, key=lambda item: item[0], reverse=True):
        out = out[:start] + replacement + out[end:]
    return out


def estimate_savings(source: str, language: str, config: StripConfig | None = None) -> float:
    """Estimate fractional token savings after stripping."""
    if not source:
        return 0.0

    stripped = strip_code(source, language, config=config)

    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        original_tokens = len(enc.encode(source))
        stripped_tokens = len(enc.encode(stripped))
    except Exception:
        original_tokens = max(1, len(source) // 4)
        stripped_tokens = len(stripped) // 4

    if original_tokens <= 0:
        return 0.0

    savings = (original_tokens - stripped_tokens) / original_tokens
    if savings < 0.0:
        return 0.0
    if savings > 1.0:
        return 1.0
    return savings

