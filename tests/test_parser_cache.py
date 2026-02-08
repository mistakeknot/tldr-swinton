"""Verify tree-sitter parser factory functions are cached."""
import pytest

# Only run if tree-sitter is available
ts = pytest.importorskip("tree_sitter")
ts_typescript = pytest.importorskip("tree_sitter_typescript")

from tldr_swinton.modules.core.cross_file_calls import _get_ts_parser


def test_ts_parser_is_cached():
    """Calling _get_ts_parser twice returns the exact same object."""
    p1 = _get_ts_parser()
    p2 = _get_ts_parser()
    assert p1 is p2, "Parser should be cached (same identity)"
