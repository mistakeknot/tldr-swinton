"""
Embedding backends for tldr-swinton semantic search.

Supports multiple embedding backends:
- Ollama (nomic-embed-text-v2-moe) - Local, fast, no download needed if Ollama running
- sentence-transformers - HuggingFace models (BGE, MiniLM, etc.)

Use Ollama for local development, sentence-transformers for production quality.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - exercised via runtime envs
    np = None  # type: ignore[assignment]
    _NUMPY_IMPORT_ERROR = exc


def _require_numpy():
    if np is None:
        raise RuntimeError(
            "NumPy is required for semantic indexing. "
            "Install with: pip install 'tldr-swinton[semantic-ollama]' "
            "or 'tldr-swinton[semantic]'."
        ) from _NUMPY_IMPORT_ERROR
    return np

# Backend types
BackendType = Literal["ollama", "sentence-transformers", "auto"]

# Configuration
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text-v2-moe")
DEFAULT_BACKEND = os.environ.get("TLDR_EMBED_BACKEND", "auto")

# Embedding dimensions by model
MODEL_DIMENSIONS = {
    # Ollama models
    "nomic-embed-text-v2-moe": 768,
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
    # sentence-transformers models
    "BAAI/bge-large-en-v1.5": 1024,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
}


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    """L2 normalize a vector for cosine similarity via inner product.

    FAISS IndexFlatIP uses inner product. For normalized vectors,
    inner product equals cosine similarity. This must be applied
    to ALL embeddings regardless of backend.
    """
    np_local = _require_numpy()
    v = v.astype(np_local.float32, copy=False)
    norm = np_local.linalg.norm(v)
    if not np_local.isfinite(norm) or norm == 0.0:
        return v
    return v / norm


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    vector: np.ndarray
    model: str
    backend: str
    dimension: int


class OllamaEmbedder:
    """Embedding backend using Ollama API."""

    def __init__(self, model: str = OLLAMA_EMBED_MODEL, host: str = OLLAMA_HOST):
        self.model = model
        self.host = host.rstrip("/")
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        if self._available is not None:
            return self._available

        try:
            import urllib.request
            import urllib.error

            # Check if Ollama is running
            url = f"{self.host}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                data = json.loads(response.read().decode())
                models = [m["name"].split(":")[0] for m in data.get("models", [])]
                self._available = self.model.split(":")[0] in models
                return self._available
        except Exception as e:
            logger.debug("Ollama availability check failed: %s", e)
            self._available = False
            return False

    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for text using Ollama API."""
        np_local = _require_numpy()
        import urllib.request
        import urllib.error

        url = f"{self.host}/api/embeddings"
        payload = json.dumps({"model": self.model, "prompt": text}).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            embedding = data["embedding"]
            return np_local.array(embedding, dtype=np_local.float32)

    def embed_batch(self, texts: list[str], max_workers: int = 8) -> list[np.ndarray]:
        """Embed multiple texts in parallel using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if len(texts) <= 1:
            return [self.embed(text) for text in texts]

        workers = min(max_workers, len(texts))
        results = [None] * len(texts)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_idx = {
                executor.submit(self.embed, text): i
                for i, text in enumerate(texts)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()

        return results


class SentenceTransformerEmbedder:
    """Embedding backend using sentence-transformers."""

    def __init__(self, model: str = "BAAI/bge-large-en-v1.5"):
        self.model_name = model
        self._model = None

    def is_available(self) -> bool:
        """Check if sentence-transformers is installed."""
        try:
            import sentence_transformers
            return True
        except ImportError:
            return False

    def _get_model(self):
        """Lazy load the model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for text."""
        np_local = _require_numpy()
        model = self._get_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return np_local.array(embedding, dtype=np_local.float32)

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed multiple texts efficiently."""
        np_local = _require_numpy()
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [np_local.array(e, dtype=np_local.float32) for e in embeddings]


def get_embedder(backend: BackendType = "auto", model: Optional[str] = None):
    """Get an embedder instance based on backend preference.

    Args:
        backend: "ollama", "sentence-transformers", or "auto"
        model: Optional model name override

    Returns:
        Embedder instance (OllamaEmbedder or SentenceTransformerEmbedder)

    Raises:
        RuntimeError: If no backend is available
    """
    if backend == "auto":
        # Try Ollama first (faster, local)
        ollama = OllamaEmbedder(model=model or OLLAMA_EMBED_MODEL)
        if ollama.is_available():
            return ollama

        # Fall back to sentence-transformers
        st = SentenceTransformerEmbedder(model=model or "BAAI/bge-large-en-v1.5")
        if st.is_available():
            return st

        raise RuntimeError(
            "No embedding backend available. Install sentence-transformers "
            "(pip install 'tldr-swinton[semantic]') or run Ollama with "
            f"{model or OLLAMA_EMBED_MODEL}."
        )

    elif backend == "ollama":
        embedder = OllamaEmbedder(model=model or OLLAMA_EMBED_MODEL)
        if not embedder.is_available():
            raise RuntimeError(
                f"Ollama not available at {OLLAMA_HOST} or model '{model or OLLAMA_EMBED_MODEL}' not found. "
                f"Run: ollama pull {model or OLLAMA_EMBED_MODEL}"
            )
        return embedder

    elif backend == "sentence-transformers":
        embedder = SentenceTransformerEmbedder(model=model or "BAAI/bge-large-en-v1.5")
        if not embedder.is_available():
            raise RuntimeError(
                "sentence-transformers not installed. Run: pip install 'tldr-swinton[semantic]'"
            )
        return embedder

    else:
        raise ValueError(f"Unknown backend: {backend}")


def embed_text(
    text: str,
    backend: BackendType = "auto",
    model: Optional[str] = None
) -> EmbeddingResult:
    """Embed text using the specified backend.

    Args:
        text: Text to embed
        backend: "ollama", "sentence-transformers", or "auto"
        model: Optional model name

    Returns:
        EmbeddingResult with L2-normalized vector and metadata
    """
    embedder = get_embedder(backend, model)
    vector = embedder.embed(text)

    # Always normalize for consistent cosine similarity via inner product
    vector = _l2_normalize(vector)

    # Determine actual model and backend used
    if isinstance(embedder, OllamaEmbedder):
        actual_backend = "ollama"
        actual_model = embedder.model
    else:
        actual_backend = "sentence-transformers"
        actual_model = embedder.model_name

    return EmbeddingResult(
        vector=vector,
        model=actual_model,
        backend=actual_backend,
        dimension=len(vector)
    )


def embed_batch(
    texts: list[str],
    backend: BackendType = "auto",
    model: Optional[str] = None,
    show_progress: bool = False
) -> list[EmbeddingResult]:
    """Embed multiple texts.

    Args:
        texts: List of texts to embed
        backend: "ollama", "sentence-transformers", or "auto"
        model: Optional model name
        show_progress: Show progress bar (requires rich)

    Returns:
        List of EmbeddingResult objects with L2-normalized vectors
    """
    embedder = get_embedder(backend, model)

    # Determine backend info
    if isinstance(embedder, OllamaEmbedder):
        actual_backend = "ollama"
        actual_model = embedder.model
    else:
        actual_backend = "sentence-transformers"
        actual_model = embedder.model_name

    def make_result(vector: np.ndarray) -> EmbeddingResult:
        """Create result with normalized vector."""
        return EmbeddingResult(
            vector=_l2_normalize(vector),
            model=actual_model,
            backend=actual_backend,
            dimension=len(vector)
        )

    # With progress
    if show_progress:
        try:
            from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

            results = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            ) as progress:
                task = progress.add_task(f"Embedding ({actual_backend})...", total=len(texts))

                # Batch for sentence-transformers, parallelized batch for Ollama
                if isinstance(embedder, SentenceTransformerEmbedder):
                    vectors = embedder.embed_batch(texts)
                    for vector in vectors:
                        results.append(make_result(vector))
                        progress.update(task, advance=1)
                else:
                    vectors = embedder.embed_batch(texts)
                    for vector in vectors:
                        results.append(make_result(vector))
                        progress.update(task, advance=1)

            return results
        except ImportError:
            pass  # Fall through to non-progress version

    # Without progress
    vectors = embedder.embed_batch(texts)
    return [make_result(v) for v in vectors]


def check_backends() -> dict:
    """Check which embedding backends are available.

    Returns:
        Dict with availability status for each backend
    """
    result = {
        "ollama": {
            "available": False,
            "host": OLLAMA_HOST,
            "model": OLLAMA_EMBED_MODEL,
        },
        "sentence-transformers": {
            "available": False,
        }
    }

    # Check Ollama
    try:
        ollama = OllamaEmbedder()
        result["ollama"]["available"] = ollama.is_available()
    except Exception as e:
        logger.debug("Error checking Ollama backend: %s", e)
        result["ollama"]["error"] = str(e)

    # Check sentence-transformers
    try:
        st = SentenceTransformerEmbedder()
        result["sentence-transformers"]["available"] = st.is_available()
    except Exception as e:
        logger.debug("Error checking sentence-transformers backend: %s", e)
        result["sentence-transformers"]["error"] = str(e)

    return result
