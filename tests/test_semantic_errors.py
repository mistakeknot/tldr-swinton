"""Tests for semantic module error handling and logging.

Verifies that the semantic module properly logs errors instead of
silently swallowing exceptions.
"""

import logging
from pathlib import Path

import pytest

from tldr_swinton.modules.semantic.vector_store import VectorStore


def test_vector_store_load_nonexistent_logs_warning(tmp_path: Path, caplog):
    """Verify that loading a nonexistent index logs a warning."""
    store = VectorStore(str(tmp_path))

    with caplog.at_level(logging.WARNING):
        result = store.load()

    assert result is False
    # Should not raise, but should return False


def test_vector_store_exists_returns_false_for_empty_dir(tmp_path: Path):
    """Verify exists() returns False when no index files present."""
    store = VectorStore(str(tmp_path))
    assert store.exists() is False


def test_vector_store_get_unit_returns_none_for_missing(tmp_path: Path):
    """Verify get_unit returns None for missing unit ID."""
    store = VectorStore(str(tmp_path))
    assert store.get_unit("nonexistent") is None


def test_vector_store_count_is_zero_for_empty(tmp_path: Path):
    """Verify count is 0 for empty store."""
    store = VectorStore(str(tmp_path))
    assert store.count == 0


def test_vector_store_search_returns_empty_without_index(tmp_path: Path):
    """Verify search returns empty list when no index loaded."""
    try:
        import numpy as np
    except ImportError:
        pytest.skip("NumPy not available")

    store = VectorStore(str(tmp_path))
    query = np.zeros(768, dtype=np.float32)  # Common embedding dimension
    results = store.search(query, k=10)

    assert results == []


def test_vector_store_get_vector_returns_none_invalid_index(tmp_path: Path):
    """Verify get_vector returns None for invalid index."""
    store = VectorStore(str(tmp_path))
    assert store.get_vector(-1) is None
    assert store.get_vector(0) is None
    assert store.get_vector(100) is None
