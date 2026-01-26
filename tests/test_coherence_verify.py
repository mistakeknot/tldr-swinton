"""Tests for multi-file coherence verification."""

import tempfile
from pathlib import Path

import pytest

from tldr_swinton.modules.core.coherence_verify import (
    CoherenceIssue,
    CoherenceReport,
    CoherenceVerifier,
    CrossFileReference,
    EditedSymbol,
    format_coherence_report_for_agent,
    verify_edit_coherence,
)


OLD_CODE = '''
def process_data(items: list[str], max_count: int) -> dict[str, int]:
    """Process items."""
    result = {}
    for item in items:
        result[item] = min(result.get(item, 0) + 1, max_count)
    return result


def helper_function(x: int) -> int:
    """Helper."""
    return x * 2
'''

NEW_CODE_COMPAT = '''
def process_data(items: list[str], max_count: int, default: int = 0) -> dict[str, int]:
    """Process items with optional default."""
    result = {}
    for item in items:
        result[item] = min(result.get(item, default) + 1, max_count)
    return result


def helper_function(x: int) -> int:
    """Helper."""
    return x * 2
'''

NEW_CODE_BREAKING = '''
def process_data(items: list[str]) -> list[int]:
    """Process items - incompatible change!"""
    return [len(item) for item in items]


def helper_function(x: int) -> int:
    """Helper."""
    return x * 2
'''


class TestEditedSymbol:
    def test_basic(self):
        symbol = EditedSymbol(
            file_path="test.py",
            symbol_name="func",
            old_signature="def func(x: int) -> int:",
            new_signature="def func(x: int, y: int) -> int:",
        )
        assert symbol.file_path == "test.py"
        assert symbol.symbol_name == "func"


class TestCoherenceVerifier:
    def test_extract_edited_symbols_no_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = CoherenceVerifier(Path(tmpdir))

            symbols = verifier.extract_edited_symbols("test.py", OLD_CODE, OLD_CODE)

            assert len(symbols) == 0

    def test_extract_edited_symbols_compatible_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = CoherenceVerifier(Path(tmpdir))

            symbols = verifier.extract_edited_symbols("test.py", OLD_CODE, NEW_CODE_COMPAT)

            # Should find one changed symbol (process_data)
            assert len(symbols) == 1
            assert symbols[0].symbol_name == "process_data"

    def test_extract_edited_symbols_breaking_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = CoherenceVerifier(Path(tmpdir))

            symbols = verifier.extract_edited_symbols("test.py", OLD_CODE, NEW_CODE_BREAKING)

            assert len(symbols) == 1
            symbol = symbols[0]
            assert symbol.symbol_name == "process_data"
            # Old had max_count param, new doesn't
            old_param_names = [p[0] for p in symbol.old_params]
            new_param_names = [p[0] for p in symbol.new_params]
            assert "max_count" in old_param_names
            assert "max_count" not in new_param_names

    def test_verify_signature_compatibility_removed_param(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = CoherenceVerifier(Path(tmpdir))

            edited_symbols = [
                EditedSymbol(
                    file_path="test.py",
                    symbol_name="process_data",
                    old_params=[("items", "list[str]"), ("max_count", "int")],
                    new_params=[("items", "list[str]")],
                )
            ]

            issues = verifier.verify_signature_compatibility(edited_symbols, [])

            assert len(issues) == 1
            assert issues[0].issue_type == "parameter_removed"
            assert issues[0].severity == "error"

    def test_verify_signature_compatibility_return_type_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = CoherenceVerifier(Path(tmpdir))

            edited_symbols = [
                EditedSymbol(
                    file_path="test.py",
                    symbol_name="process_data",
                    old_return_type="dict[str, int]",
                    new_return_type="list[int]",
                    old_params=[("items", "list[str]")],
                    new_params=[("items", "list[str]")],
                )
            ]

            issues = verifier.verify_signature_compatibility(edited_symbols, [])

            assert len(issues) == 1
            assert issues[0].issue_type == "return_type_changed"
            assert issues[0].severity == "warning"

    def test_verify_import_consistency_removed_symbol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = CoherenceVerifier(Path(tmpdir))

            edited_symbols = [
                EditedSymbol(
                    file_path="test.py",
                    symbol_name="old_function",
                    old_signature="def old_function(): ...",
                    new_signature=None,  # Removed
                )
            ]

            issues = verifier.verify_import_consistency(["test.py"], edited_symbols)

            assert len(issues) == 1
            assert issues[0].issue_type == "symbol_removed"

    def test_verify_coherence_no_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = CoherenceVerifier(Path(tmpdir))

            edits = {
                "test.py": (OLD_CODE, NEW_CODE_COMPAT),
            }

            report = verifier.verify_coherence(edits)

            assert report.is_coherent
            assert len(report.edited_files) == 1

    def test_verify_coherence_with_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = CoherenceVerifier(Path(tmpdir))

            edits = {
                "test.py": (OLD_CODE, NEW_CODE_BREAKING),
            }

            report = verifier.verify_coherence(edits)

            assert not report.is_coherent
            assert len(report.issues) > 0


class TestCoherenceReport:
    def test_to_dict(self):
        report = CoherenceReport(
            is_coherent=True,
            issues=[],
            edited_files=["a.py", "b.py"],
            dependencies_checked=5,
            cross_file_refs_found=3,
        )

        d = report.to_dict()

        assert d["is_coherent"] is True
        assert len(d["edited_files"]) == 2

    def test_summary_coherent(self):
        report = CoherenceReport(
            is_coherent=True,
            issues=[],
            edited_files=["a.py"],
            dependencies_checked=1,
            cross_file_refs_found=0,
        )

        summary = report.summary()

        assert "All edits are coherent" in summary

    def test_summary_with_errors(self):
        report = CoherenceReport(
            is_coherent=False,
            issues=[
                CoherenceIssue(
                    severity="error",
                    issue_type="parameter_removed",
                    message="Removed param x from func",
                    source_file="test.py",
                )
            ],
            edited_files=["test.py"],
            dependencies_checked=1,
            cross_file_refs_found=1,
        )

        summary = report.summary()

        assert "error(s) found" in summary
        assert "FAILED" in summary


class TestVerifyEditCoherence:
    def test_convenience_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            edits = {
                "test.py": (OLD_CODE, NEW_CODE_COMPAT),
            }

            report = verify_edit_coherence(project, edits)

            assert report.is_coherent


class TestFormatCoherenceReport:
    def test_format_coherent(self):
        report = CoherenceReport(
            is_coherent=True,
            issues=[],
            edited_files=["a.py"],
            dependencies_checked=1,
            cross_file_refs_found=0,
        )

        output = format_coherence_report_for_agent(report)

        assert "# Multi-File Coherence Verification" in output
        assert "Result: PASS" in output
        assert "No issues found" in output

    def test_format_with_issues(self):
        report = CoherenceReport(
            is_coherent=False,
            issues=[
                CoherenceIssue(
                    severity="error",
                    issue_type="parameter_removed",
                    message="Removed param x from func",
                    source_file="test.py",
                    source_symbol="func",
                    suggested_fix="Update callers",
                )
            ],
            edited_files=["test.py"],
            dependencies_checked=1,
            cross_file_refs_found=1,
        )

        output = format_coherence_report_for_agent(report)

        assert "## Issues Found" in output
        assert "parameter_removed" in output
        assert "ERROR" in output
        assert "Suggested fix" in output
        assert "Result: FAIL" in output
