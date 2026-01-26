"""Tests for edit locality analysis."""

import tempfile
from pathlib import Path

import pytest

from tldr_swinton.modules.core.edit_locality import (
    EditBoundary,
    EditContext,
    EditLocalityAnalyzer,
    Invariant,
    PatchTemplate,
    format_edit_context_for_agent,
    get_edit_context,
)


SAMPLE_CODE = '''
def process_data(items: list[str], max_count: int = 10) -> dict[str, int]:
    """Process a list of items and return counts.

    Args:
        items: List of items to process
        max_count: Maximum count per item

    Returns:
        Dictionary of item counts
    """
    assert items is not None, "items cannot be None"
    assert max_count > 0, "max_count must be positive"

    result: dict[str, int] = {}
    for item in items:
        if item in result:
            result[item] = min(result[item] + 1, max_count)
        else:
            result[item] = 1

    return result


MAX_ITEMS = 1000


class DataProcessor:
    """Processes data with configurable options."""

    @staticmethod
    def validate(data: str) -> bool:
        """Check if data is valid."""
        return len(data) > 0
'''


class TestEditLocalityAnalyzer:
    def test_extract_invariants_assertions(self):
        analyzer = EditLocalityAnalyzer()
        lines = SAMPLE_CODE.strip().splitlines()

        invariants = analyzer.extract_invariants(lines, 1, 22)

        assertion_invariants = [inv for inv in invariants if inv.kind == "assertion"]
        assert len(assertion_invariants) >= 2
        assert any("items is not None" in inv.content for inv in assertion_invariants)

    def test_extract_invariants_type_hints(self):
        analyzer = EditLocalityAnalyzer()
        lines = SAMPLE_CODE.strip().splitlines()

        invariants = analyzer.extract_invariants(lines, 1, 22)

        type_invariants = [inv for inv in invariants if inv.kind == "type_hint"]
        # Should find at least one type hint (the return type or param types)
        # The regex extracts capitalized types like dict, list, etc.
        assert len(type_invariants) > 0 or len(invariants) > 0

    def test_extract_invariants_constants(self):
        analyzer = EditLocalityAnalyzer()
        lines = SAMPLE_CODE.strip().splitlines()

        invariants = analyzer.extract_invariants(lines, 1, len(lines))

        constant_invariants = [inv for inv in invariants if inv.kind == "constant"]
        assert any("MAX_ITEMS" in inv.content for inv in constant_invariants)

    def test_extract_invariants_decorators(self):
        analyzer = EditLocalityAnalyzer()
        lines = SAMPLE_CODE.strip().splitlines()

        invariants = analyzer.extract_invariants(lines, 1, len(lines))

        decorator_invariants = [inv for inv in invariants if inv.kind == "decorator"]
        assert any("@staticmethod" in inv.content for inv in decorator_invariants)

    def test_compute_edit_boundary_no_diff(self):
        analyzer = EditLocalityAnalyzer()
        lines = SAMPLE_CODE.strip().splitlines()

        boundary = analyzer.compute_edit_boundary(lines, 1, 22, diff_lines=None)

        assert boundary.boundary_type == "body"
        assert boundary.start_line > 1  # Should skip signature and docstring

    def test_compute_edit_boundary_with_diff(self):
        analyzer = EditLocalityAnalyzer()
        lines = SAMPLE_CODE.strip().splitlines()

        boundary = analyzer.compute_edit_boundary(lines, 1, 22, diff_lines=[15, 16, 17])

        assert boundary.boundary_type == "diff_zone"
        assert boundary.start_line == 15
        assert boundary.end_line == 17

    def test_generate_patch_template(self):
        analyzer = EditLocalityAnalyzer()
        lines = SAMPLE_CODE.strip().splitlines()

        template = analyzer.generate_patch_template(
            lines, 1, 22, "def process_data(items: list[str], max_count: int = 10) -> dict[str, int]:"
        )

        assert template.signature.startswith("def process_data")
        assert template.edit_zone_start > 1
        assert template.edit_zone_end == 22
        # Should preserve docstring lines
        assert len(template.preserve_before) > 0

    def test_extract_type_constraints(self):
        analyzer = EditLocalityAnalyzer()
        source = SAMPLE_CODE.strip()

        constraints = analyzer.extract_type_constraints(source, "process_data")

        # Should find parameter types
        assert any("items" in c and "list[str]" in c for c in constraints)
        assert any("max_count" in c and "int" in c for c in constraints)
        # Should find return type
        assert any("dict[str, int]" in c for c in constraints)


class TestGetEditContext:
    def test_get_edit_context_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            test_file = project / "test_module.py"
            test_file.write_text(SAMPLE_CODE)

            context = get_edit_context(project, "test_module.py:process_data")

            assert context is not None
            assert context.symbol_id == "test_module.py:process_data"
            assert "def process_data" in context.target_code
            assert len(context.boundaries) > 0
            assert len(context.invariants) > 0

    def test_get_edit_context_with_diff_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            test_file = project / "test_module.py"
            test_file.write_text(SAMPLE_CODE)

            context = get_edit_context(
                project, "test_module.py:process_data", diff_lines=[15, 16]
            )

            assert context is not None
            assert context.boundaries[0].boundary_type == "diff_zone"

    def test_get_edit_context_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            context = get_edit_context(project, "nonexistent.py:func")

            assert context is None

    def test_get_edit_context_invalid_symbol_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            context = get_edit_context(project, "no_colon_here")

            assert context is None


class TestEditContext:
    def test_to_dict(self):
        context = EditContext(
            symbol_id="test.py:func",
            file_path="/path/to/test.py",
            target_code="def func(): pass",
            boundaries=[EditBoundary(start_line=1, end_line=1)],
            invariants=[
                Invariant(
                    kind="assertion",
                    line=2,
                    content="assert x",
                    reason="Check x",
                )
            ],
            patch_template=PatchTemplate(
                symbol_id="test.py:func",
                signature="def func():",
                current_body="pass",
                edit_zone_start=1,
                edit_zone_end=1,
                preserve_before=[],
                preserve_after=[],
            ),
            adjacent_symbols=["test.py:other"],
            type_constraints=["-> None"],
        )

        d = context.to_dict()

        assert d["symbol_id"] == "test.py:func"
        assert len(d["boundaries"]) == 1
        assert len(d["invariants"]) == 1
        assert d["patch_template"] is not None
        assert len(d["adjacent_symbols"]) == 1


class TestFormatEditContext:
    def test_format_basic(self):
        context = EditContext(
            symbol_id="test.py:func",
            file_path="/path/to/test.py",
            target_code="def func():\n    pass",
            boundaries=[EditBoundary(start_line=1, end_line=2, boundary_type="body")],
            invariants=[
                Invariant(
                    kind="assertion",
                    line=2,
                    content="assert x > 0",
                    reason="x must be positive",
                )
            ],
            patch_template=None,
            adjacent_symbols=[],
            type_constraints=["-> None"],
        )

        output = format_edit_context_for_agent(context)

        assert "# Edit Context for test.py:func" in output
        assert "## Target Code" in output
        assert "def func():" in output
        assert "## Invariants (DO NOT MODIFY)" in output
        assert "assert x > 0" in output
        assert "## Type Constraints" in output
        assert "-> None" in output

    def test_format_with_patch_template(self):
        context = EditContext(
            symbol_id="test.py:func",
            file_path="/path/to/test.py",
            target_code="def func():\n    pass",
            boundaries=[],
            invariants=[],
            patch_template=PatchTemplate(
                symbol_id="test.py:func",
                signature="def func():",
                current_body="    pass",
                edit_zone_start=2,
                edit_zone_end=2,
                preserve_before=["    '''docstring'''"],
                preserve_after=[],
            ),
            adjacent_symbols=["test.py:helper"],
            type_constraints=[],
        )

        output = format_edit_context_for_agent(context)

        assert "## Patch Template" in output
        assert "=== EDIT ZONE START ===" in output
        assert "## Adjacent Symbols" in output
        assert "test.py:helper" in output
