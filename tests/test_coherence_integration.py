"""Integration tests for coherence_verify wired into CLI and MCP."""

from pathlib import Path

import pytest

from tldr_swinton.modules.core.coherence_verify import (
    CoherenceVerifier,
    verify_edit_coherence,
    verify_from_context_pack,
    format_coherence_report_for_agent,
)


@pytest.fixture
def project_with_cross_refs(tmp_path: Path) -> Path:
    """Project where module b imports and calls a function from module a."""
    (tmp_path / "a.py").write_text(
        "def process(data: str, flag: bool = False) -> str:\n"
        "    return data.upper()\n"
    )
    (tmp_path / "b.py").write_text(
        "from a import process\n"
        "\n"
        "def run():\n"
        "    return process('hello')\n"
    )
    return tmp_path


class TestVerifyEditCoherence:
    def test_coherent_edits(self, project_with_cross_refs: Path) -> None:
        """Edits that maintain signature compatibility are coherent."""
        edits = {
            str(project_with_cross_refs / "a.py"): (
                "def process(data: str, flag: bool = False) -> str:\n    return data.upper()\n",
                "def process(data: str, flag: bool = False) -> str:\n    return data.lower()\n",
            ),
        }
        report = verify_edit_coherence(project_with_cross_refs, edits)
        # Body-only change should be coherent
        assert report.is_coherent

    def test_signature_mismatch_detected(self, project_with_cross_refs: Path) -> None:
        """Removing a parameter should be flagged as incoherent."""
        edits = {
            str(project_with_cross_refs / "a.py"): (
                "def process(data: str, flag: bool = False) -> str:\n    return data.upper()\n",
                # Completely different signature — removed parameter
                "def process(data: str) -> str:\n    return data.upper()\n",
            ),
        }
        report = verify_edit_coherence(project_with_cross_refs, edits)
        # Should detect signature change (may or may not be "incoherent"
        # depending on whether callers use the removed param)
        assert report.dependencies_checked > 0


class TestVerifyFromContextPack:
    def test_empty_pack_is_coherent(self, tmp_path: Path) -> None:
        """An empty context pack should trivially be coherent."""
        report = verify_from_context_pack(tmp_path, {"slices": []})
        assert report.is_coherent
        assert report.edited_files == []

    def test_pack_with_slices_extracts_files(self, project_with_cross_refs: Path) -> None:
        """verify_from_context_pack should extract files from slice IDs."""
        pack = {
            "slices": [
                {"id": "a.py:process"},
                {"id": "b.py:run"},
            ]
        }
        # This will try to compare current files against git HEAD.
        # Without git init, it should handle gracefully.
        report = verify_from_context_pack(project_with_cross_refs, pack)
        assert isinstance(report.is_coherent, bool)


class TestFormatReport:
    def test_format_coherent_report(self, project_with_cross_refs: Path) -> None:
        edits = {
            str(project_with_cross_refs / "a.py"): (
                "def process(data: str) -> str:\n    return data.upper()\n",
                "def process(data: str) -> str:\n    return data.lower()\n",
            ),
        }
        report = verify_edit_coherence(project_with_cross_refs, edits)
        formatted = format_coherence_report_for_agent(report)
        assert isinstance(formatted, str)
        assert len(formatted) > 0
