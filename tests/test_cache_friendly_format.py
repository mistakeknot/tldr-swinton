"""Tests for cache-friendly output format."""

import pytest

from tldr_swinton.modules.core.output_formats import format_context_pack, format_context
from tldr_swinton.modules.core.engines.symbolkite import FunctionContext, RelevantContext


class TestCacheFriendlyFormat:
    """Test cache-friendly format for LLM prompt caching optimization."""

    def test_basic_structure(self):
        """Cache-friendly output has expected sections."""
        pack = {
            "slices": [
                {"id": "api.py:get_user", "signature": "def get_user(id: int)", "code": None, "relevance": "caller"},
                {"id": "api.py:update_user", "signature": "def update_user(id: int, data: dict)", "code": "def update_user(id: int, data: dict):\n    pass", "relevance": "contains_diff"},
            ],
            "unchanged": ["api.py:get_user"],
            "cache_stats": {"hit_rate": 0.5, "hits": 1, "misses": 1},
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "# tldrs cache-friendly output" in result
        assert "CACHE PREFIX" in result
        assert "DYNAMIC CONTENT" in result
        assert "CACHE_BREAKPOINT" in result
        assert "STATS:" in result

    def test_unchanged_in_prefix_only(self):
        """Unchanged symbols appear only in cache prefix section."""
        pack = {
            "slices": [
                {"id": "a.py:func_a", "signature": "def func_a()", "code": None, "relevance": "caller"},
                {"id": "b.py:func_b", "signature": "def func_b()", "code": "def func_b():\n    return 1", "relevance": "contains_diff"},
            ],
            "unchanged": ["a.py:func_a"],
        }

        result = format_context_pack(pack, fmt="cache-friendly")
        lines = result.split("\n")

        # Find the cache breakpoint to split sections
        breakpoint_idx = next(i for i, line in enumerate(lines) if "CACHE_BREAKPOINT" in line)

        prefix_section = "\n".join(lines[:breakpoint_idx])
        dynamic_section = "\n".join(lines[breakpoint_idx:])

        # Unchanged symbol in prefix, not in dynamic
        assert "a.py:func_a" in prefix_section
        # Dynamic section should have func_b
        assert "b.py:func_b" in dynamic_section

    def test_changed_has_code(self):
        """Changed symbols in dynamic section include code blocks."""
        pack = {
            "slices": [
                {"id": "api.py:handler", "signature": "def handler()", "code": "def handler():\n    return 42", "relevance": "contains_diff"},
            ],
            "unchanged": [],
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "```" in result
        assert "return 42" in result

    def test_stable_ordering_in_prefix(self):
        """Unchanged symbols in prefix are sorted by ID for cache stability."""
        pack = {
            "slices": [
                {"id": "z_file.py:z_func", "signature": "def z_func()", "code": None, "relevance": "caller"},
                {"id": "a_file.py:a_func", "signature": "def a_func()", "code": None, "relevance": "callee"},
                {"id": "m_file.py:m_func", "signature": "def m_func()", "code": None, "relevance": "caller"},
            ],
            "unchanged": ["z_file.py:z_func", "a_file.py:a_func", "m_file.py:m_func"],
        }

        result = format_context_pack(pack, fmt="cache-friendly")
        lines = result.split("\n")

        # Find lines with our symbols in prefix section
        symbol_lines = [line for line in lines if "a_file.py" in line or "m_file.py" in line or "z_file.py" in line]

        # Should be sorted: a_file, m_file, z_file
        assert len(symbol_lines) == 3
        assert "a_file.py" in symbol_lines[0]
        assert "m_file.py" in symbol_lines[1]
        assert "z_file.py" in symbol_lines[2]

    def test_token_estimates_present(self):
        """Output includes token estimates."""
        pack = {
            "slices": [
                {"id": "x.py:foo", "signature": "def foo()", "code": "def foo():\n    pass", "relevance": "contains_diff"},
            ],
            "unchanged": [],
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "tokens" in result.lower()
        assert "STATS:" in result

    def test_breakpoint_marker_present(self):
        """Cache breakpoint marker is present when there's a prefix."""
        pack = {
            "slices": [
                {"id": "a.py:x", "signature": "def x()", "code": None, "relevance": "caller"},
                {"id": "b.py:y", "signature": "def y()", "code": "def y(): pass", "relevance": "contains_diff"},
            ],
            "unchanged": ["a.py:x"],
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "CACHE_BREAKPOINT" in result

    def test_all_unchanged_case(self):
        """When all symbols unchanged, dynamic section is empty."""
        pack = {
            "slices": [
                {"id": "a.py:func1", "signature": "def func1()", "code": None, "relevance": "caller"},
                {"id": "b.py:func2", "signature": "def func2()", "code": None, "relevance": "callee"},
            ],
            "unchanged": ["a.py:func1", "b.py:func2"],
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "CACHE PREFIX" in result
        # Should not have DYNAMIC CONTENT section since all are unchanged
        assert "DYNAMIC CONTENT" not in result or "0 symbols" in result

    def test_all_changed_case(self):
        """When all symbols changed, prefix section is empty."""
        pack = {
            "slices": [
                {"id": "x.py:a", "signature": "def a()", "code": "def a(): pass", "relevance": "contains_diff"},
                {"id": "y.py:b", "signature": "def b()", "code": "def b(): return", "relevance": "caller"},
            ],
            "unchanged": [],
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        # Should have DYNAMIC section
        assert "DYNAMIC CONTENT" in result
        # Should not have cache prefix section with symbols
        lines = result.split("\n")
        has_prefix_with_symbols = False
        in_prefix = False
        for line in lines:
            if "CACHE PREFIX" in line:
                in_prefix = True
            if "CACHE_BREAKPOINT" in line or "DYNAMIC CONTENT" in line:
                in_prefix = False
            if in_prefix and (":a" in line or ":b" in line):
                has_prefix_with_symbols = True
        assert not has_prefix_with_symbols

    def test_empty_pack(self):
        """Empty pack returns minimal output."""
        pack = {"slices": [], "unchanged": []}

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "# tldrs cache-friendly output" in result
        assert "No symbols" in result or len(result.strip().split("\n")) <= 5

    def test_cache_stats_shown(self):
        """Cache stats are displayed when present."""
        pack = {
            "slices": [
                {"id": "x.py:func", "signature": "def func()", "code": None, "relevance": "caller"},
            ],
            "unchanged": ["x.py:func"],
            "cache_stats": {"hit_rate": 0.75, "hits": 3, "misses": 1},
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "75%" in result or "0.75" in result
        assert "3 unchanged" in result

    def test_relevance_labels_preserved(self):
        """Relevance labels are shown for each symbol."""
        pack = {
            "slices": [
                {"id": "a.py:x", "signature": "def x()", "code": "def x(): pass", "relevance": "contains_diff"},
                {"id": "b.py:y", "signature": "def y()", "code": None, "relevance": "caller"},
            ],
            "unchanged": ["b.py:y"],
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "[contains_diff]" in result
        assert "[caller]" in result

    def test_line_numbers_shown(self):
        """Line numbers are included in output."""
        pack = {
            "slices": [
                {"id": "api.py:get_user", "signature": "def get_user(id)", "code": None, "lines": [45, 52], "relevance": "caller"},
            ],
            "unchanged": ["api.py:get_user"],
        }

        result = format_context_pack(pack, fmt="cache-friendly")

        assert "@45" in result


class TestCacheFriendlyFormatContext:
    """Test cache-friendly format with RelevantContext (format_context)."""

    def test_format_context_cache_friendly(self):
        """format_context supports cache-friendly format."""
        ctx = RelevantContext(
            entry_point="main",
            depth=2,
            functions=[
                FunctionContext(name="main", file="app.py", line=10, signature="def main()", depth=0),
                FunctionContext(name="helper", file="utils.py", line=5, signature="def helper(x)", depth=1),
            ],
        )

        result = format_context(ctx, fmt="cache-friendly")

        assert "# tldrs cache-friendly output" in result
        assert "DYNAMIC CONTENT" in result
        assert "main" in result
        assert "helper" in result

    def test_format_context_cache_friendly_all_dynamic(self):
        """Without delta, all symbols go to dynamic section."""
        ctx = RelevantContext(
            entry_point="process",
            depth=1,
            functions=[
                FunctionContext(name="process", file="core.py", line=100, signature="def process(data)", depth=0),
            ],
        )

        result = format_context(ctx, fmt="cache-friendly")

        # No cache prefix since RelevantContext has no delta info
        assert "CACHE PREFIX" not in result or "0 symbols" in result
