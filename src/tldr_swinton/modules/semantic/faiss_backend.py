"""
FAISS single-vector search backend.

Consolidates the embedding (Ollama / sentence-transformers) and FAISS
vector-storage logic into a single SearchBackend implementation.

Supports:
- Ollama (nomic-embed-text-v2-moe) — local, fast
- sentence-transformers — HuggingFace models (BGE, MiniLM, etc.)
- Incremental indexing with file-hash change detection
- Hybrid search via BM25 Reciprocal Rank Fusion
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Literal

from .backend import (
    BackendInfo,
    BackendStats,
    CodeUnit,
    SearchResult,
    META_FILENAME,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text-v2-moe")

EmbedBackendType = Literal["ollama", "sentence-transformers", "auto"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_numpy():
    try:
        import numpy as np
        return np
    except ImportError as exc:
        raise RuntimeError(
            "NumPy is required for FAISS backend. "
            "Install with: pip install 'tldr-swinton[semantic-ollama]' "
            "or 'tldr-swinton[semantic]'."
        ) from exc


def _require_faiss():
    try:
        import faiss
        return faiss
    except ImportError as exc:
        raise RuntimeError(
            "FAISS is required. "
            "Install with: pip install 'tldr-swinton[semantic-ollama]' "
            "or 'tldr-swinton[semantic]'."
        ) from exc


def _l2_normalize(v):
    """L2 normalize a vector for cosine similarity via inner product."""
    np = _require_numpy()
    v = v.astype(np.float32, copy=False)
    norm = np.linalg.norm(v)
    if not np.isfinite(norm) or norm == 0.0:
        return v
    return v / norm


# ---------------------------------------------------------------------------
# Embedders (inlined from old embeddings.py)
# ---------------------------------------------------------------------------


class _OllamaEmbedder:
    """Embedding backend using Ollama API."""

    def __init__(self, model: str = OLLAMA_EMBED_MODEL, host: str = OLLAMA_HOST):
        self.model = model
        self.host = host.rstrip("/")
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import urllib.request
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

    def embed(self, text: str):
        np = _require_numpy()
        import urllib.request
        url = f"{self.host}/api/embeddings"
        payload = json.dumps({"model": self.model, "prompt": text}).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            return np.array(data["embedding"], dtype=np.float32)

    def embed_batch(self, texts: list[str], max_workers: int = 8):
        if len(texts) <= 1:
            return [self.embed(t) for t in texts]
        workers = min(max_workers, len(texts))
        results = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futs = {executor.submit(self.embed, t): i for i, t in enumerate(texts)}
            for future in as_completed(futs):
                results[futs[future]] = future.result()
        return results


class _SentenceTransformerEmbedder:
    """Embedding backend using sentence-transformers."""

    def __init__(self, model: str = "BAAI/bge-large-en-v1.5"):
        self.model_name = model
        self._model = None

    def is_available(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, text: str):
        np = _require_numpy()
        model = self._get_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return np.array(embedding, dtype=np.float32)

    def embed_batch(self, texts: list[str]):
        np = _require_numpy()
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [np.array(e, dtype=np.float32) for e in embeddings]


def _get_embedder(
    backend: EmbedBackendType = "auto",
    model: Optional[str] = None,
):
    """Get an embedder instance."""
    if backend == "auto":
        ollama = _OllamaEmbedder(model=model or OLLAMA_EMBED_MODEL)
        if ollama.is_available():
            return ollama
        st = _SentenceTransformerEmbedder(model=model or "BAAI/bge-large-en-v1.5")
        if st.is_available():
            return st
        raise RuntimeError(
            "No embedding backend available. Install sentence-transformers "
            "(pip install 'tldr-swinton[semantic]') or run Ollama with "
            f"{model or OLLAMA_EMBED_MODEL}."
        )
    elif backend == "ollama":
        embedder = _OllamaEmbedder(model=model or OLLAMA_EMBED_MODEL)
        if not embedder.is_available():
            raise RuntimeError(
                f"Ollama not available at {OLLAMA_HOST} or model "
                f"'{model or OLLAMA_EMBED_MODEL}' not found."
            )
        return embedder
    elif backend == "sentence-transformers":
        embedder = _SentenceTransformerEmbedder(model=model or "BAAI/bge-large-en-v1.5")
        if not embedder.is_available():
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Run: pip install 'tldr-swinton[semantic]'"
            )
        return embedder
    else:
        raise ValueError(f"Unknown embedding backend: {backend}")


# ---------------------------------------------------------------------------
# Internal vector-store metadata
# ---------------------------------------------------------------------------


@dataclass
class _VectorStoreMetadata:
    """Metadata persisted in meta.json for FAISS indexes."""
    version: str = "1.0"
    backend: str = "faiss"
    embed_model: str = ""
    embed_backend: str = ""
    dimension: int = 0
    count: int = 0
    project_root: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "_VectorStoreMetadata":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# FAISSBackend
# ---------------------------------------------------------------------------


class FAISSBackend:
    """FAISS single-vector search backend.

    Self-contained: embeds text via Ollama or sentence-transformers,
    stores in a FAISS IndexFlatIP index, supports incremental updates
    and hybrid BM25 fusion.
    """

    INDEX_DIR = ".tldrs/index"

    def __init__(
        self,
        project_path: str,
        embed_backend: EmbedBackendType = "auto",
        embed_model: Optional[str] = None,
    ):
        self.project = Path(project_path).resolve()
        self.index_dir = self.project / self.INDEX_DIR
        self._embed_backend = embed_backend
        self._embed_model = embed_model

        # In-memory state (protected by _instance_lock for concurrent access)
        self._instance_lock = threading.RLock()
        self._faiss_index = None
        self._units: list[CodeUnit] = []
        self._id_to_idx: dict[str, int] = {}
        self._metadata = _VectorStoreMetadata(project_root=str(self.project))

    # -- File paths --

    @property
    def _index_path(self) -> Path:
        return self.index_dir / "vectors.faiss"

    @property
    def _units_path(self) -> Path:
        return self.index_dir / "units.json"

    @property
    def _meta_path(self) -> Path:
        return self.index_dir / META_FILENAME

    @property
    def _lock_path(self) -> Path:
        return self.index_dir / ".build.lock"

    @property
    def _sentinel_path(self) -> Path:
        return self.index_dir / ".build_in_progress"

    # -- SearchBackend interface --

    def build(
        self,
        units: list[CodeUnit],
        texts: list[str],
        *,
        rebuild: bool = False,
    ) -> BackendStats:
        """Build or incrementally update the FAISS index."""
        faiss = _require_faiss()
        np = _require_numpy()

        stats = BackendStats(backend_name="faiss")

        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Acquire build lock (non-blocking)
        lock_fd = self._acquire_build_lock()
        try:
            # Write sentinel
            self._sentinel_path.touch()

            # Load existing index for incremental update
            existing_units: dict[str, CodeUnit] = {}
            existing_vectors: dict[str, any] = {}

            if not rebuild and self._index_path.exists():
                if self.load():
                    old_vectors = self._reconstruct_all_vectors()
                    for i, unit in enumerate(self._units):
                        existing_units[unit.id] = unit
                        if i < len(old_vectors):
                            existing_vectors[unit.id] = old_vectors[i]

            # Partition units
            units_to_embed = []
            texts_to_embed = []
            all_units = []
            all_vectors = []
            embed_indices = []

            for unit, text in zip(units, texts):
                existing = existing_units.get(unit.id)
                existing_vec = existing_vectors.get(unit.id)

                if (
                    existing
                    and existing.file_hash == unit.file_hash
                    and existing_vec is not None
                ):
                    all_units.append(unit)
                    all_vectors.append(existing_vec)
                    stats.unchanged_units += 1
                else:
                    all_units.append(unit)
                    all_vectors.append(None)  # placeholder
                    embed_indices.append(len(all_vectors) - 1)
                    units_to_embed.append(unit)
                    texts_to_embed.append(text)
                    if existing:
                        stats.updated_units += 1
                    else:
                        stats.new_units += 1

            stats.total_units = len(all_units)

            if not units_to_embed:
                # Nothing changed
                return stats

            # Embed new/changed texts
            embedder = _get_embedder(self._embed_backend, self._embed_model)
            if isinstance(embedder, _OllamaEmbedder):
                raw_vecs = embedder.embed_batch(texts_to_embed)
                stats.embed_model = embedder.model
                stats.backend_name = "faiss"
            else:
                raw_vecs = embedder.embed_batch(texts_to_embed)
                stats.embed_model = embedder.model_name
                stats.backend_name = "faiss"

            # L2 normalize and fill in placeholders
            for i, vec in zip(embed_indices, raw_vecs):
                all_vectors[i] = _l2_normalize(vec)

            # Build FAISS index
            matrix = np.vstack(all_vectors).astype(np.float32)
            dimension = matrix.shape[1]
            new_index = faiss.IndexFlatIP(dimension)
            new_index.add(matrix)

            # Atomically swap in-memory state so concurrent search() sees
            # a consistent snapshot (index + units + id_to_idx together).
            actual_backend = "ollama" if isinstance(embedder, _OllamaEmbedder) else "sentence-transformers"
            actual_model = embedder.model if isinstance(embedder, _OllamaEmbedder) else embedder.model_name
            with self._instance_lock:
                self._faiss_index = new_index
                self._units = all_units
                self._id_to_idx = {u.id: i for i, u in enumerate(self._units)}
                self._metadata = _VectorStoreMetadata(
                    backend="faiss",
                    embed_model=actual_model,
                    embed_backend=actual_backend,
                    dimension=dimension,
                    count=len(all_units),
                    project_root=str(self.project),
                )
            stats.embed_model = actual_model

            # Remove sentinel on success
            self._sentinel_path.unlink(missing_ok=True)
            return stats

        finally:
            self._release_build_lock(lock_fd)

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        """Search the FAISS index with optional BM25 RRF fusion."""
        # Snapshot state under lock to prevent seeing partial updates
        # from a concurrent build().
        with self._instance_lock:
            faiss_index = self._faiss_index
            units = self._units
            metadata = self._metadata

        if faiss_index is None or not units:
            return []

        np = _require_numpy()

        # Embed query
        embedder = _get_embedder(
            self._embed_backend if self._embed_backend != "auto" else metadata.embed_backend or "auto",
            self._embed_model or metadata.embed_model or None,
        )
        query_vec = _l2_normalize(embedder.embed(query))
        query_arr = query_vec.reshape(1, -1).astype(np.float32)

        # FAISS search (uses snapshotted index)
        actual_k = min(k, len(units))
        scores, indices = faiss_index.search(query_arr, actual_k)

        semantic_results = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx < 0 or idx >= len(units):
                continue
            semantic_results.append(SearchResult(
                unit=units[idx], score=float(score), rank=rank,
            ))

        # Try BM25 hybrid fusion
        bm25_results: list[tuple[str, float]] = []
        try:
            from .bm25_store import BM25Store
            bm25 = BM25Store(self.index_dir)
            if bm25.load():
                bm25_results = bm25.search(query, k=k)
        except (ImportError, Exception) as e:
            logger.debug("BM25 search unavailable: %s", e)

        if bm25_results:
            return self._rrf_fuse(semantic_results, bm25_results, k)

        return semantic_results[:k]

    def load(self) -> bool:
        """Load existing FAISS index from disk."""
        if not self._index_path.exists() or not self._units_path.exists():
            # Check for partial build
            if self._sentinel_path.exists():
                logger.warning("Partial FAISS build detected, needs rebuild")
                self._sentinel_path.unlink(missing_ok=True)
            return False

        try:
            faiss = _require_faiss()
            self._faiss_index = faiss.read_index(str(self._index_path))
            units_data = json.loads(self._units_path.read_text())
            self._units = [CodeUnit.from_dict(u) for u in units_data]
            self._id_to_idx = {u.id: i for i, u in enumerate(self._units)}

            if self._meta_path.exists():
                self._metadata = _VectorStoreMetadata.from_dict(
                    json.loads(self._meta_path.read_text())
                )
            return True
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
            logger.warning("Failed to load FAISS index from %s: %s", self.index_dir, e)
            return False

    def save(self) -> None:
        """Persist FAISS index, units, and metadata to disk."""
        faiss = _require_faiss()
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        if self._faiss_index is not None:
            faiss.write_index(self._faiss_index, str(self._index_path))

        # Save units
        units_data = [u.to_dict() for u in self._units]
        self._units_path.write_text(json.dumps(units_data, indent=2))

        # Atomic meta.json write
        self._metadata.count = len(self._units)
        self._write_meta_atomic(self._metadata.to_dict())

    def info(self) -> BackendInfo:
        return BackendInfo(
            backend_name="faiss",
            model=self._metadata.embed_model,
            dimension=self._metadata.dimension,
            count=len(self._units),
            index_path=str(self.index_dir),
            extra={
                "embed_backend": self._metadata.embed_backend,
            },
        )

    # -- Public helpers (used by index.py for backward compat) --

    def get_unit(self, unit_id: str) -> Optional[CodeUnit]:
        idx = self._id_to_idx.get(unit_id)
        if idx is not None:
            return self._units[idx]
        return None

    def get_all_units(self) -> list[CodeUnit]:
        return list(self._units)

    def get_units_by_name(self, name: str) -> list[CodeUnit]:
        return [u for u in self._units if u.name == name]

    # -- Internal methods --

    def _reconstruct_all_vectors(self):
        np = _require_numpy()
        if self._faiss_index is None or not self._units:
            return np.zeros((0, 0), dtype=np.float32)
        try:
            return self._faiss_index.reconstruct_n(0, len(self._units))
        except RuntimeError as e:
            logger.warning("Batch vector reconstruction failed, falling back to per-vector: %s", e)
            vectors = []
            for i in range(len(self._units)):
                vectors.append(self._faiss_index.reconstruct(i))
            return np.vstack(vectors).astype(np.float32)

    def _rrf_fuse(
        self,
        semantic_results: list[SearchResult],
        bm25_results: list[tuple[str, float]],
        k: int,
        k_param: int = 60,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion of semantic and BM25 results."""
        scores: dict[str, float] = {}
        units_map: dict[str, CodeUnit] = {}

        for rank, result in enumerate(semantic_results):
            uid = result.unit.id
            scores[uid] = scores.get(uid, 0.0) + 1.0 / (k_param + rank + 1)
            units_map[uid] = result.unit

        for rank, (uid, _score) in enumerate(bm25_results):
            scores[uid] = scores.get(uid, 0.0) + 1.0 / (k_param + rank + 1)
            if uid not in units_map:
                unit = self.get_unit(uid)
                if unit:
                    units_map[uid] = unit

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            SearchResult(unit=units_map[uid], score=score, rank=i)
            for i, (uid, score) in enumerate(ranked)
            if uid in units_map
        ][:k]

    def _write_meta_atomic(self, data: dict) -> None:
        """Write meta.json atomically via temp file + rename."""
        tmp = self._meta_path.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self._meta_path)

    def _acquire_build_lock(self):
        """Acquire non-blocking exclusive lock for build serialization."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        fd = open(self._lock_path, "w")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fd.close()
            raise RuntimeError(
                "Another build is in progress. "
                "Wait for it to finish or remove .tldrs/index/.build.lock"
            )
        return fd

    def _release_build_lock(self, fd) -> None:
        if fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                fd.close()
            except Exception:
                pass
