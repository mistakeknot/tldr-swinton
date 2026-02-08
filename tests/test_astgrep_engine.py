"""Tests for the ast-grep structural search engine."""

import pytest


def test_astgrep_module_importable():
    """The astgrep engine module is importable even without ast-grep-py."""
    # This should not raise — the module uses lazy imports
    try:
        from tldr_swinton.modules.core.engines.astgrep import get_structural_search  # noqa: F401
    except ImportError:
        pytest.skip("ast-grep-py not installed")


def test_astgrep_ext_to_lang_mapping():
    """Extension to language mapping covers common languages."""
    from tldr_swinton.modules.core.engines.astgrep import _EXT_TO_LANG

    assert _EXT_TO_LANG[".py"] == "python"
    assert _EXT_TO_LANG[".ts"] == "typescript"
    assert _EXT_TO_LANG[".go"] == "go"
    assert _EXT_TO_LANG[".rs"] == "rust"


def test_structural_matches_to_candidates():
    """Structural matches convert to Candidate objects."""
    from tldr_swinton.modules.core.engines.astgrep import (
        StructuralMatch,
        structural_matches_to_candidates,
    )

    matches = [
        StructuralMatch(file="a.py", line=10, end_line=12, text="def foo(): pass"),
        StructuralMatch(file="b.py", line=20, end_line=25, text="class Bar: ..."),
    ]
    candidates = structural_matches_to_candidates(matches)
    assert len(candidates) == 2
    assert candidates[0].symbol_id == "a.py:10"
    assert candidates[0].relevance_label == "structural-match"
    assert candidates[1].code == "class Bar: ..."


def test_check_astgrep():
    """_check_astgrep returns bool without raising."""
    from tldr_swinton.modules.core.engines.astgrep import _check_astgrep

    result = _check_astgrep()
    assert isinstance(result, bool)
