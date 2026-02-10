"""Hierarchical zoom levels for progressive disclosure."""
from __future__ import annotations

import enum
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .contextpack_engine import Candidate


class ZoomLevel(enum.Enum):
    L0 = 0  # Module map: file list + 1-line descriptions
    L1 = 1  # Symbol index: signatures + docstring first line
    L2 = 2  # Body sketch: control flow skeleton (tree-sitter)
    L3 = 3  # Windowed body: diff-relevant code windows
    L4 = 4  # Full body: current default

    @classmethod
    def from_string(cls, s: str) -> "ZoomLevel":
        return cls[s.upper()]


_LANGUAGE_ALIASES = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "jsx": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "typescript": "typescript",
    "go": "go",
}

_DEFINITION_NODES: dict[str, set[str]] = {
    "python": {"function_definition", "async_function_definition", "class_definition"},
    "javascript": {"function_declaration", "method_definition", "class_declaration", "arrow_function"},
    "typescript": {"function_declaration", "method_definition", "class_declaration", "arrow_function"},
    "go": {"function_declaration", "method_declaration"},
}

_CONTROL_KEYWORDS: dict[str, dict[str, str]] = {
    "python": {
        "if_statement": "if",
        "elif_clause": "elif",
        "else_clause": "else",
        "for_statement": "for",
        "while_statement": "while",
        "try_statement": "try",
        "except_clause": "except",
        "finally_clause": "finally",
        "with_statement": "with",
        "match_statement": "match",
        "case_clause": "case",
        "return_statement": "return",
        "yield": "yield",
        "yield_from": "yield",
        "raise_statement": "raise",
    },
    "javascript": {
        "if_statement": "if",
        "else_clause": "else",
        "for_statement": "for",
        "while_statement": "while",
        "try_statement": "try",
        "catch_clause": "catch",
        "finally_clause": "finally",
        "switch_statement": "switch",
        "switch_case": "case",
        "switch_default": "case",
        "return_statement": "return",
        "throw_statement": "throw",
    },
    "typescript": {
        "if_statement": "if",
        "else_clause": "else",
        "for_statement": "for",
        "while_statement": "while",
        "try_statement": "try",
        "catch_clause": "catch",
        "finally_clause": "finally",
        "switch_statement": "switch",
        "switch_case": "case",
        "switch_default": "case",
        "return_statement": "return",
        "throw_statement": "throw",
    },
    "go": {
        "if_statement": "if",
        "for_statement": "for",
        "switch_statement": "switch",
        "type_switch_statement": "switch",
        "select_statement": "select",
        "case_clause": "case",
        "communication_case": "case",
        "return_statement": "return",
        "go_statement": "go",
        "defer_statement": "defer",
    },
}


def _normalize_language(language: str) -> str:
    return _LANGUAGE_ALIASES.get((language or "").lower(), (language or "").lower())


@lru_cache(maxsize=None)
def _tree_sitter_language(language: str):
    norm = _normalize_language(language)
    try:
        from tree_sitter import Language
    except Exception:
        return None

    try:
        if norm == "python":
            import tree_sitter_python

            return Language(tree_sitter_python.language())
        if norm == "javascript":
            import tree_sitter_javascript

            return Language(tree_sitter_javascript.language())
        if norm == "typescript":
            import tree_sitter_typescript

            return Language(tree_sitter_typescript.language_typescript())
        if norm == "go":
            import tree_sitter_go

            return Language(tree_sitter_go.language())
    except Exception:
        return None
    return None


@lru_cache(maxsize=None)
def _get_parser(language: str):
    norm = _normalize_language(language)
    lang = _tree_sitter_language(norm)
    if lang is None:
        return None
    try:
        from tree_sitter import Parser

        parser = Parser()
        parser.language = lang
        return parser
    except Exception:
        try:
            from tree_sitter import Parser

            return Parser(lang)
        except Exception:
            return None


def _indent_for_node(node, source_lines: list[str]) -> str:
    row = node.start_point[0]
    if row < 0 or row >= len(source_lines):
        return ""
    line = source_lines[row]
    indent_width = len(line) - len(line.lstrip(" \t"))
    return line[:indent_width]


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _clean_signature(node_type: str, text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    first = lines[0].rstrip(";")
    if node_type == "arrow_function":
        left = first.split("=>", 1)[0].strip()
        if left:
            return f"arrow {left} =>"
        return "arrow =>"
    first = first.split("{", 1)[0].rstrip()
    first = first.rstrip(":").rstrip()
    return first


def _sketch_line(node, source_bytes: bytes, source_lines: list[str], language: str) -> str | None:
    norm = _normalize_language(language)
    node_type = node.type

    if node_type in _DEFINITION_NODES.get(norm, set()):
        signature = _clean_signature(node_type, _node_text(node, source_bytes))
        if not signature:
            return None
        return f"{_indent_for_node(node, source_lines)}{signature}"

    keyword = _CONTROL_KEYWORDS.get(norm, {}).get(node_type)
    if keyword:
        return f"{_indent_for_node(node, source_lines)}{keyword}"
    return None


def extract_body_sketch(source: str, language: str) -> str:
    """Extract control-flow skeleton from source using tree-sitter."""
    norm = _normalize_language(language)
    if norm not in _CONTROL_KEYWORDS:
        return ""
    parser = _get_parser(norm)
    if parser is None:
        return ""
    if not source.strip():
        return ""

    source_bytes = source.encode("utf-8", errors="replace")
    source_lines = source.splitlines()
    try:
        tree = parser.parse(source_bytes)
    except Exception:
        return ""

    emitted: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()

    def walk(node) -> None:
        line = _sketch_line(node, source_bytes, source_lines, norm)
        if line is not None:
            key = (node.start_byte, line)
            if key not in seen:
                seen.add(key)
                emitted.append(key)
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    emitted.sort(key=lambda item: item[0])
    return "\n".join(line for _, line in emitted).strip()


def _join_zoom_parts(*parts: str | None) -> str:
    return "\n".join(part for part in parts if part)


def format_at_zoom(
    symbol_id: str,
    signature: str,
    code: str | None,
    zoom: ZoomLevel,
    language: str = "python",
) -> str:
    """Format symbol content for a specific zoom level."""
    if zoom is ZoomLevel.L0:
        return symbol_id
    if zoom is ZoomLevel.L1:
        return _join_zoom_parts(symbol_id, signature)
    if zoom is ZoomLevel.L2:
        sketch = extract_body_sketch(code or "", language)
        return _join_zoom_parts(symbol_id, signature, sketch)
    if zoom is ZoomLevel.L3:
        return _join_zoom_parts(symbol_id, signature, code or "")
    if zoom is ZoomLevel.L4:
        return _join_zoom_parts(symbol_id, signature, code or "")
    raise ValueError(f"Unsupported zoom level: {zoom}")
