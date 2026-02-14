"""
Semantic: Vector-based code search using embeddings.

Provides semantic search capabilities for code using multiple backends:
- FAISS: Single-vector search with Ollama or sentence-transformers embeddings
- ColBERT: Multi-vector late-interaction search via PyLate

Key features:
- `tldrs index .` - Build semantic index for a project
- `tldrs find "query"` - Search code by natural language

Backends:
- pip install 'tldr-swinton[semantic-ollama]' for FAISS + Ollama
- pip install 'tldr-swinton[semantic]' for FAISS + sentence-transformers
- pip install 'tldr-swinton[semantic-colbert]' for ColBERT (best quality, ~1.7GB)
"""

__version__ = "0.1.0"

# Re-export main APIs
from .index import build_index, search_index, get_index_info, IndexStats
from .backend import (
    SearchBackend,
    get_backend,
    BackendStats,
    BackendInfo,
    CodeUnit,
    SearchResult,
    make_unit_id,
    get_file_hash,
)
from .bm25_store import BM25Store

__all__ = [
    # Index operations
    "build_index",
    "search_index",
    "get_index_info",
    "IndexStats",
    # Backend abstraction
    "SearchBackend",
    "get_backend",
    "BackendStats",
    "BackendInfo",
    # Shared types
    "CodeUnit",
    "SearchResult",
    "make_unit_id",
    "get_file_hash",
    # BM25 store
    "BM25Store",
]
