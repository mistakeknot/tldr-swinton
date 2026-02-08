"""
Semantic: Vector-based code search using embeddings.

Provides semantic search capabilities for code using:
- Multiple embedding backends (Ollama, sentence-transformers)
- FAISS for efficient vector similarity search
- Incremental indexing with content-based caching

Key features:
- `tldrs index .` - Build semantic index for a project
- `tldrs find "query"` - Search code by natural language

Requires optional dependencies:
- pip install 'tldr-swinton[semantic-ollama]' for Ollama backend
- pip install 'tldr-swinton[semantic]' for sentence-transformers backend
"""

__version__ = "0.1.0"

# Re-export main APIs
from .index import build_index, search_index, get_index_info, IndexStats
from .embeddings import (
    embed_batch,
    embed_text,
    check_backends,
    BackendType,
)
from .vector_store import VectorStore, CodeUnit, make_unit_id, get_file_hash
from .bm25_store import BM25Store

__all__ = [
    # Index operations
    "build_index",
    "search_index",
    "get_index_info",
    "IndexStats",
    # Embeddings
    "embed_batch",
    "embed_text",
    "check_backends",
    "BackendType",
    # Vector store
    "VectorStore",
    "CodeUnit",
    "make_unit_id",
    "get_file_hash",
    # BM25 store
    "BM25Store",
]
