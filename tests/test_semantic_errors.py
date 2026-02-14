"""Tests for semantic module error handling and logging.

Verifies that the FAISS backend properly handles missing/empty indexes.
"""

import logging
from pathlib import Path

import pytest

from tldr_swinton.modules.semantic.faiss_backend import FAISSBackend


def test_faiss_load_nonexistent_returns_false(tmp_path: Path, caplog):
    """Verify that loading a nonexistent index returns False."""
    store = FAISSBackend(str(tmp_path))

    with caplog.at_level(logging.WARNING):
        result = store.load()

    assert result is False


def test_faiss_empty_has_zero_units(tmp_path: Path):
    """Verify a fresh backend has no units."""
    store = FAISSBackend(str(tmp_path))
    assert len(store.get_all_units()) == 0


def test_faiss_get_unit_returns_none_for_missing(tmp_path: Path):
    """Verify get_unit returns None for missing unit ID."""
    store = FAISSBackend(str(tmp_path))
    assert store.get_unit("nonexistent") is None
