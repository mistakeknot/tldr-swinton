"""
Backward-compatibility shim.

Real implementation lives in faiss_backend.py. This module re-exports
the public API that external code (evals, AGENTS.md examples) relies on.
"""

from __future__ import annotations

from typing import Literal

from .faiss_backend import (
    _OllamaEmbedder as OllamaEmbedder,
    _SentenceTransformerEmbedder as SentenceTransformerEmbedder,
    _get_embedder as get_embedder,
    _l2_normalize,
    _require_numpy,
    OLLAMA_HOST,
    OLLAMA_EMBED_MODEL,
    EmbedBackendType,
)

BackendType = EmbedBackendType

# Re-export these so `from tldr_swinton.embeddings import check_backends` works
from dataclasses import dataclass
import numpy as np


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    vector: np.ndarray
    model: str
    backend: str
    dimension: int


def embed_text(text, backend="auto", model=None):
    """Embed text using the specified backend."""
    embedder = get_embedder(backend, model)
    vector = _l2_normalize(embedder.embed(text))
    if isinstance(embedder, OllamaEmbedder):
        return EmbeddingResult(vector=vector, model=embedder.model, backend="ollama", dimension=len(vector))
    return EmbeddingResult(vector=vector, model=embedder.model_name, backend="sentence-transformers", dimension=len(vector))


def embed_batch(texts, backend="auto", model=None, show_progress=False):
    """Embed multiple texts."""
    embedder = get_embedder(backend, model)
    if isinstance(embedder, OllamaEmbedder):
        actual_backend = "ollama"
        actual_model = embedder.model
    else:
        actual_backend = "sentence-transformers"
        actual_model = embedder.model_name

    vectors = embedder.embed_batch(texts)
    return [
        EmbeddingResult(
            vector=_l2_normalize(v), model=actual_model,
            backend=actual_backend, dimension=len(v),
        )
        for v in vectors
    ]


def check_backends():
    """Check which embedding backends are available."""
    result = {
        "ollama": {"available": False, "host": OLLAMA_HOST, "model": OLLAMA_EMBED_MODEL},
        "sentence-transformers": {"available": False},
    }
    try:
        ollama = OllamaEmbedder()
        result["ollama"]["available"] = ollama.is_available()
    except Exception:
        pass
    try:
        st = SentenceTransformerEmbedder()
        result["sentence-transformers"]["available"] = st.is_available()
    except Exception:
        pass
    return result
