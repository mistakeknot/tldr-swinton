"""Tests for shared ProjectIndex reuse across engine calls.

Verifies that when a pre-built _project_index is passed to engine functions,
ProjectIndex.build() is NOT called again, and all functions produce correct
results using the shared index.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import pytest

from tldr_swinton.modules.core.project_index import ProjectIndex

# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal Python project with cross-file calls."""
    (tmp_path / "a.py").write_text(
        "from b import helper\n\n"
        "def process(x):\n"
        "    return helper(x)\n"
    )
    (tmp_path / "b.py").write_text(
        "def helper(x):\n"
        "    return x + 1\n\n"
        "class Converter:\n"
        "    def convert(self, x):\n"
        "        return str(x)\n"
    )
    return tmp_path


@pytest.fixture
def built_index(project_dir: Path):
    """Build a ProjectIndex with all flags enabled for the test project."""
    return ProjectIndex.build(
        project_dir, "python",
        include_sources=True,
        include_ranges=True,
        include_reverse_adjacency=True,
    )


# ── Tests ─────────────────────────────────────────────────────────────

class TestSymbolkiteReusesIndex:
    """Verify symbolkite functions use the provided index and don't rebuild."""

    def test_get_relevant_context_reuses_provided_index(self, project_dir, built_index):
        from tldr_swinton.modules.core.engines.symbolkite import get_relevant_context

        with patch.object(ProjectIndex, "build", wraps=ProjectIndex.build) as mock_build:
            ctx = get_relevant_context(
                project_dir, "process", depth=1, language="python",
                _project_index=built_index,
            )
            mock_build.assert_not_called()
            assert ctx.functions is not None
            assert len(ctx.functions) > 0

    def test_get_context_pack_reuses_provided_index(self, project_dir, built_index):
        from tldr_swinton.modules.core.engines.symbolkite import get_context_pack

        with patch.object(ProjectIndex, "build", wraps=ProjectIndex.build) as mock_build:
            result = get_context_pack(
                project_dir, "process", depth=1, language="python",
                _project_index=built_index,
            )
            mock_build.assert_not_called()
            assert "slices" in result

    def test_get_signatures_for_entry_reuses_provided_index(self, project_dir, built_index):
        from tldr_swinton.modules.core.engines.symbolkite import get_signatures_for_entry

        with patch.object(ProjectIndex, "build", wraps=ProjectIndex.build) as mock_build:
            sigs = get_signatures_for_entry(
                project_dir, "process", depth=1, language="python",
                _project_index=built_index,
            )
            mock_build.assert_not_called()
            assert isinstance(sigs, list)
            assert len(sigs) > 0


class TestDifflensReusesIndex:
    """Verify difflens functions use the provided index and don't rebuild."""

    def test_map_hunks_uses_index_ranges(self, project_dir, built_index):
        """map_hunks_to_symbols should use symbol_ranges from the index, not HybridExtractor."""
        from tldr_swinton.modules.core.engines.difflens import map_hunks_to_symbols

        hunks = [("a.py", 3, 4)]  # Lines inside process()

        with patch(
            "tldr_swinton.modules.core.engines.difflens.HybridExtractor"
        ) as mock_extractor_cls:
            result = map_hunks_to_symbols(
                project_dir, hunks, language="python",
                _project_index=built_index,
            )
            # HybridExtractor should NOT be instantiated — fast path used
            mock_extractor_cls.assert_not_called()
            # Should still find the symbol
            assert len(result) > 0

    def test_build_diff_context_reuses_provided_index(self, project_dir, built_index):
        from tldr_swinton.modules.core.engines.difflens import build_diff_context_from_hunks

        hunks = [("a.py", 3, 4)]

        with patch.object(ProjectIndex, "build", wraps=ProjectIndex.build) as mock_build:
            result = build_diff_context_from_hunks(
                project_dir, hunks, language="python",
                _project_index=built_index,
            )
            mock_build.assert_not_called()
            assert "slices" in result

    def test_get_diff_signatures_reuses_provided_index(self, project_dir, built_index):
        from tldr_swinton.modules.core.engines.difflens import get_diff_signatures

        hunks = [("a.py", 3, 4)]

        with patch.object(ProjectIndex, "build", wraps=ProjectIndex.build) as mock_build:
            sigs = get_diff_signatures(
                project_dir, hunks, language="python",
                _project_index=built_index,
            )
            mock_build.assert_not_called()
            assert isinstance(sigs, list)


class TestBackwardCompatibility:
    """Verify all functions work when _project_index=None (default behavior)."""

    def test_symbolkite_works_without_index(self, project_dir):
        from tldr_swinton.modules.core.engines.symbolkite import get_relevant_context

        ctx = get_relevant_context(
            project_dir, "process", depth=1, language="python",
        )
        assert ctx.functions is not None
        assert len(ctx.functions) > 0

    def test_map_hunks_works_without_index(self, project_dir):
        from tldr_swinton.modules.core.engines.difflens import map_hunks_to_symbols

        hunks = [("a.py", 3, 4)]
        result = map_hunks_to_symbols(
            project_dir, hunks, language="python",
        )
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_api_wrappers_accept_project_index(self, project_dir, built_index):
        from tldr_swinton.modules.core.api import get_symbol_context_pack

        with patch.object(ProjectIndex, "build", wraps=ProjectIndex.build) as mock_build:
            result = get_symbol_context_pack(
                project_dir, "process", depth=1, language="python",
                _project_index=built_index,
            )
            mock_build.assert_not_called()
            assert "slices" in result
