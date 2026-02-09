"""Integration tests for edit_locality wired into ContextPackEngine."""

from pathlib import Path

import pytest

from tldr_swinton.modules.core.edit_locality import create_edit_locality_enricher
from tldr_swinton.modules.core.contextpack_engine import Candidate


def _make_candidate(
    symbol_id: str,
    lines: tuple[int, int] | None = None,
    meta: dict | None = None,
) -> Candidate:
    return Candidate(
        symbol_id=symbol_id,
        relevance=5,
        relevance_label="test",
        order=0,
        signature=f"def {symbol_id.split(':')[-1]}()",
        lines=lines,
        meta=meta,
    )


@pytest.fixture
def project_with_source(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Create a project with source files and return file_sources map."""
    source = (
        "def foo():\n"
        "    x = 1\n"
        "    y = 2\n"
        "    return x + y\n"
        "\n"
        "def bar():\n"
        "    assert True\n"
        "    return 42\n"
    )
    (tmp_path / "mod.py").write_text(source)
    file_sources = {str(tmp_path / "mod.py"): source}
    return tmp_path, file_sources


class TestEditLocalityEnricher:
    def test_enricher_adds_metadata_for_diff_candidates(
        self, project_with_source: tuple[Path, dict]
    ) -> None:
        """Candidates with diff_lines should get edit_boundary and invariants."""
        project, file_sources = project_with_source

        enricher = create_edit_locality_enricher(str(project), file_sources)

        candidates = [
            _make_candidate(
                "mod.py:foo",
                lines=(1, 4),
                meta={"diff_lines": [[2, 3]]},  # Lines 2-3 changed
            ),
        ]
        result = enricher(candidates)

        assert len(result) == 1
        meta = result[0].meta
        assert "edit_boundary" in meta
        assert "start" in meta["edit_boundary"]
        assert "end" in meta["edit_boundary"]
        assert "type" in meta["edit_boundary"]
        assert "invariants" in meta

    def test_enricher_skips_candidates_without_diff(
        self, project_with_source: tuple[Path, dict]
    ) -> None:
        """Candidates without diff_lines should pass through unchanged."""
        project, file_sources = project_with_source

        enricher = create_edit_locality_enricher(str(project), file_sources)

        candidates = [
            _make_candidate("mod.py:bar", lines=(6, 8)),
        ]
        result = enricher(candidates)

        assert len(result) == 1
        # No edit_boundary or invariants added
        meta = result[0].meta
        assert meta is None or "edit_boundary" not in (meta or {})

    def test_enricher_handles_integer_diff_lines(
        self, project_with_source: tuple[Path, dict]
    ) -> None:
        """diff_lines can be individual integers, not just ranges."""
        project, file_sources = project_with_source

        enricher = create_edit_locality_enricher(str(project), file_sources)

        candidates = [
            _make_candidate(
                "mod.py:foo",
                lines=(1, 4),
                meta={"diff_lines": [2, 3]},  # Individual line numbers
            ),
        ]
        result = enricher(candidates)
        assert "edit_boundary" in result[0].meta

    def test_enricher_preserves_candidate_count(
        self, project_with_source: tuple[Path, dict]
    ) -> None:
        project, file_sources = project_with_source
        enricher = create_edit_locality_enricher(str(project), file_sources)

        candidates = [
            _make_candidate("mod.py:foo", lines=(1, 4), meta={"diff_lines": [[2, 3]]}),
            _make_candidate("mod.py:bar", lines=(6, 8)),
        ]
        result = enricher(candidates)
        assert len(result) == 2

    def test_enricher_caps_invariants_at_5(
        self, project_with_source: tuple[Path, dict]
    ) -> None:
        """Invariants list is capped at 5 to avoid bloat."""
        project, file_sources = project_with_source
        enricher = create_edit_locality_enricher(str(project), file_sources)

        candidates = [
            _make_candidate(
                "mod.py:foo",
                lines=(1, 4),
                meta={"diff_lines": [[1, 4]]},
            ),
        ]
        result = enricher(candidates)
        if result[0].meta and "invariants" in result[0].meta:
            assert len(result[0].meta["invariants"]) <= 5
