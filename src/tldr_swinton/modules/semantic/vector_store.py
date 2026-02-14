"""
Backward-compatibility shim.

Real implementation lives in backend.py (shared types) and faiss_backend.py
(VectorStore equivalent). This module re-exports the public API.
"""

from __future__ import annotations

# Shared types (now in backend.py)
from .backend import CodeUnit, SearchResult, make_unit_id, get_file_hash

# VectorStore is now internal to FAISSBackend, but evals reference it.
# Re-export the dataclass that was used for metadata.
from .faiss_backend import _VectorStoreMetadata as VectorStoreMetadata

# For eval scripts that import VectorStore directly
from .faiss_backend import FAISSBackend as VectorStore

__all__ = [
    "CodeUnit",
    "SearchResult",
    "make_unit_id",
    "get_file_hash",
    "VectorStoreMetadata",
    "VectorStore",
]
