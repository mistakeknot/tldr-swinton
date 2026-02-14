"""
ColBERT late-interaction search backend via PyLate.

Uses the LateOn-Code-edge model (17M params, 48d per token) for
code-specialized semantic search with per-token multi-vector retrieval
and PLAID indexing.

Requires: pip install 'tldr-swinton[semantic-colbert]'
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from .backend import (
    BackendInfo,
    BackendStats,
    CodeUnit,
    SearchResult,
    META_FILENAME,
)

logger = logging.getLogger(__name__)


class ColBERTBackend:
    """ColBERT late-interaction search backend via PyLate.

    Uses LateOn-Code-edge (17M params) with PLAID indexing for
    efficient multi-vector retrieval.  The model is lazy-loaded
    and kept resident in the process for daemon use (~900 MB RSS).
    """

    MODEL = "lightonai/LateOn-Code-edge"
    POOL_FACTOR = int(os.environ.get("TLDRS_COLBERT_POOL_FACTOR", "2"))
    INDEX_SUBDIR = "plaid"
    REBUILD_THRESHOLD = 0.20  # rebuild when >= 20% units deleted
    REBUILD_MAX_INCREMENTAL = 50  # force rebuild after N incremental updates (centroid drift)

    def __init__(self, project_path: str):
        self.project = Path(project_path).resolve()
        self.index_dir = self.project / ".tldrs" / "index" / self.INDEX_SUBDIR
        self._model = None  # Lazy-loaded, kept resident
        self._instance_lock = threading.RLock()
        self._index = None
        self._retriever = None
        self._units: dict[str, CodeUnit] = {}  # id -> unit
        self._unit_hashes: dict[str, str] = {}  # id -> file_hash
        self._incremental_updates: int = 0

    # -- File paths --

    @property
    def _meta_path(self) -> Path:
        return self.index_dir / META_FILENAME

    @property
    def _lock_path(self) -> Path:
        return self.index_dir / ".build.lock"

    @property
    def _sentinel_path(self) -> Path:
        return self.index_dir / ".build_in_progress"

    @property
    def _parent_meta_path(self) -> Path:
        """Top-level meta.json (shared with FAISS for backend detection)."""
        return self.project / ".tldrs" / "index" / META_FILENAME

    # -- Model loading --

    def _ensure_model(self):
        """Lazy-load PyLate model (kept resident in process)."""
        if self._model is None:
            logger.info("Loading ColBERT model (%s, first query only, ~17s)...", self.MODEL)
            from pylate import models
            self._model = models.ColBERT(model_name_or_path=self.MODEL)

    # -- SearchBackend interface --

    def build(
        self,
        units: list[CodeUnit],
        texts: list[str],
        *,
        rebuild: bool = False,
    ) -> BackendStats:
        """Build or incrementally update the PLAID index."""
        from pylate import indexes

        self._ensure_model()
        stats = BackendStats(
            backend_name="colbert",
            embed_model=self.MODEL,
        )

        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Acquire build lock
        lock_fd = self._acquire_build_lock()
        try:
            self._sentinel_path.touch()

            # Build lookup of incoming units
            incoming = {u.id: (u, t) for u, t in zip(units, texts)}
            stats.total_units = len(incoming)

            # Load existing metadata if not rebuilding
            needs_full_rebuild = rebuild
            existing_ids = set()

            if not rebuild and self._meta_path.exists():
                try:
                    meta = json.loads(self._meta_path.read_text())
                    self._units = {
                        u["id"]: CodeUnit.from_dict(u)
                        for u in meta.get("units", [])
                    }
                    self._unit_hashes = meta.get("hashes", {})
                    self._incremental_updates = meta.get("incremental_updates", 0)
                    existing_ids = set(self._units.keys())
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning("Failed to load ColBERT metadata: %s", e)
                    needs_full_rebuild = True

            # Partition into new, changed, unchanged, deleted
            new_ids = set()
            changed_ids = set()
            unchanged_ids = set()

            for uid, (unit, text) in incoming.items():
                if uid not in existing_ids:
                    new_ids.add(uid)
                elif self._unit_hashes.get(uid) != unit.file_hash:
                    changed_ids.add(uid)
                else:
                    unchanged_ids.add(uid)

            deleted_ids = existing_ids - set(incoming.keys())

            stats.new_units = len(new_ids)
            stats.updated_units = len(changed_ids)
            stats.unchanged_units = len(unchanged_ids)

            # Check rebuild threshold (PLAID can't delete)
            if deleted_ids and not needs_full_rebuild:
                deletion_ratio = len(deleted_ids) / max(len(existing_ids), 1)
                if deletion_ratio >= self.REBUILD_THRESHOLD:
                    logger.info(
                        "Deletion ratio %.1f%% >= threshold %.0f%%, triggering full rebuild",
                        deletion_ratio * 100, self.REBUILD_THRESHOLD * 100,
                    )
                    needs_full_rebuild = True

            # Enforce centroid drift limit: force rebuild after too many
            # incremental updates (PLAID centroids become stale).
            if self._incremental_updates >= self.REBUILD_MAX_INCREMENTAL and not needs_full_rebuild:
                logger.info(
                    "Index has %d incremental updates (>= %d limit), "
                    "forcing full rebuild for quality.",
                    self._incremental_updates, self.REBUILD_MAX_INCREMENTAL,
                )
                needs_full_rebuild = True
            elif self._incremental_updates >= 20 and not needs_full_rebuild:
                logger.warning(
                    "Index has %d incremental updates since last rebuild. "
                    "Consider --rebuild for best quality.",
                    self._incremental_updates,
                )

            # Determine which texts to encode
            ids_to_encode = list(new_ids | changed_ids) if not needs_full_rebuild else list(incoming.keys())
            texts_to_encode = [
                incoming[uid][1] for uid in ids_to_encode
            ]

            if not texts_to_encode and not needs_full_rebuild:
                # Nothing changed
                self._sentinel_path.unlink(missing_ok=True)
                return stats

            # Encode documents
            logger.info("Encoding %d documents with ColBERT...", len(texts_to_encode))
            doc_embeddings = self._model.encode(
                texts_to_encode,
                is_query=False,
                batch_size=32,
                pool_factor=self.POOL_FACTOR,
            )

            if needs_full_rebuild:
                # Full rebuild: build in temp dir, atomic swap
                self._build_fresh_index(
                    indexes, ids_to_encode, doc_embeddings, incoming,
                )
                self._incremental_updates = 0
            else:
                # Incremental: add new/changed docs
                self._incremental_add(
                    indexes, ids_to_encode, doc_embeddings, incoming,
                    unchanged_ids, deleted_ids,
                )
                self._incremental_updates += 1

            self._sentinel_path.unlink(missing_ok=True)
            return stats

        finally:
            self._release_build_lock(lock_fd)

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        """Search using ColBERT late interaction."""
        self._ensure_model()

        if self._retriever is None:
            if not self.load():
                return []

        # Snapshot state under lock for concurrent safety
        with self._instance_lock:
            retriever = self._retriever
            units = dict(self._units)  # shallow copy for consistent read

        if retriever is None:
            return []

        # Encode query
        query_embeddings = self._model.encode(
            [query], is_query=True,
        )

        # Retrieve using snapshotted retriever
        try:
            results = retriever.retrieve(
                query_embeddings, k=min(k, len(units)),
            )
        except Exception as e:
            logger.warning("ColBERT retrieval failed: %s", e)
            return []

        # Map results back to CodeUnits (using snapshotted units)
        search_results = []
        for rank, result_list in enumerate(results):
            for item in result_list:
                doc_id = str(item.get("id", ""))
                score = float(item.get("score", 0.0))
                unit = units.get(doc_id)
                if unit:
                    search_results.append(SearchResult(
                        unit=unit, score=score, rank=rank,
                    ))

        # Sort by score descending and assign ranks
        search_results.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(search_results):
            r.rank = i

        return search_results[:k]

    def load(self) -> bool:
        """Load existing PLAID index and metadata."""
        # Check for partial build under lock to avoid TOCTOU with
        # a concurrent build that may be writing the sentinel.
        with self._instance_lock:
            if self._sentinel_path.exists():
                logger.warning("Partial ColBERT build detected, needs rebuild")
                self._cleanup_partial()
                return False

        if not self._meta_path.exists():
            return False

        try:
            meta = json.loads(self._meta_path.read_text())
            self._units = {
                u["id"]: CodeUnit.from_dict(u)
                for u in meta.get("units", [])
            }
            self._unit_hashes = meta.get("hashes", {})
            self._incremental_updates = meta.get("incremental_updates", 0)

            if not self._units:
                return False

            # Load PLAID index
            from pylate import indexes, retrieve

            self._index = indexes.PLAID(
                index_name=str(self.index_dir),
                override=False,
            )
            self._retriever = retrieve.ColBERT(index=self._index)

            return True
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
            logger.warning("Failed to load ColBERT index: %s", e)
            return False

    def save(self) -> None:
        """Persist metadata (PLAID index auto-persists)."""
        self.index_dir.mkdir(parents=True, exist_ok=True)

        meta_data = {
            "backend": "colbert",
            "model": self.MODEL,
            "pool_factor": self.POOL_FACTOR,
            "count": len(self._units),
            "incremental_updates": self._incremental_updates,
            "units": [u.to_dict() for u in self._units.values()],
            "hashes": self._unit_hashes,
        }

        # Write top-level meta.json FIRST — it's the source of truth for
        # backend detection via _read_index_backend(). Writing it before PLAID
        # meta prevents a race where concurrent get_backend("auto") reads stale
        # backend type during the gap between the two writes.
        top_meta = {
            "backend": "colbert",
            "version": "1.0",
            "embed_model": self.MODEL,
            "embed_backend": "colbert",
            "dimension": 48,  # LateOn-Code-edge token dimension
            "count": len(self._units),
        }
        top_meta_path = self._parent_meta_path
        top_meta_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_meta_atomic(top_meta_path, top_meta)

        # Then write detailed PLAID meta
        self._write_meta_atomic(self._meta_path, meta_data)

    def info(self) -> BackendInfo:
        return BackendInfo(
            backend_name="colbert",
            model=self.MODEL,
            dimension=48,  # Per-token dimension
            count=len(self._units),
            index_path=str(self.index_dir),
            extra={
                "pool_factor": self.POOL_FACTOR,
                "incremental_updates": self._incremental_updates,
            },
        )

    # -- Internal methods --

    def _build_fresh_index(self, indexes_mod, ids, embeddings, incoming):
        """Build a fresh PLAID index in a temp dir, then atomic swap."""
        # Build in temp dir
        temp_dir = self.index_dir.parent / f"plaid-build-{os.getpid()}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        old_dir = self.index_dir.parent / "plaid-old"
        try:
            index = indexes_mod.PLAID(
                index_name=str(temp_dir),
                override=True,
            )
            index.add_documents(
                documents_ids=ids,
                documents_embeddings=embeddings,
            )

            # Atomic swap
            if self.index_dir.exists():
                if old_dir.exists():
                    shutil.rmtree(old_dir)
                self.index_dir.rename(old_dir)

            temp_dir.rename(self.index_dir)

            # Update in-memory state atomically for concurrent search()
            from pylate import retrieve
            new_retriever = retrieve.ColBERT(index=index)
            with self._instance_lock:
                self._units = {uid: incoming[uid][0] for uid in ids}
                self._unit_hashes = {uid: incoming[uid][0].file_hash for uid in ids}
                self._index = index
                self._retriever = new_retriever

        except Exception:
            raise
        finally:
            # Clean up old and temp dirs regardless of success/failure.
            # On success: old_dir lingers if retrieve.ColBERT() fails after rename.
            # On failure: temp_dir lingers if build fails partway through.
            if old_dir.exists():
                shutil.rmtree(old_dir, ignore_errors=True)
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _incremental_add(
        self, indexes_mod, ids_to_encode, embeddings, incoming,
        unchanged_ids, deleted_ids,
    ):
        """Incrementally add new/changed documents to existing PLAID index."""
        from pylate import retrieve

        if self._index is None:
            # Need to load existing index first
            self._index = indexes_mod.PLAID(
                index_name=str(self.index_dir),
                override=False,
            )

        # Add new/changed documents
        if ids_to_encode and embeddings is not None:
            self._index.add_documents(
                documents_ids=ids_to_encode,
                documents_embeddings=embeddings,
            )

        # Update in-memory state atomically for concurrent search()
        new_retriever = retrieve.ColBERT(index=self._index)
        with self._instance_lock:
            for uid in ids_to_encode:
                self._units[uid] = incoming[uid][0]
                self._unit_hashes[uid] = incoming[uid][0].file_hash
            for uid in deleted_ids:
                self._units.pop(uid, None)
                self._unit_hashes.pop(uid, None)
            self._retriever = new_retriever

    def _cleanup_partial(self):
        """Remove partial build artifacts."""
        self._sentinel_path.unlink(missing_ok=True)
        # Don't delete the whole index dir — might have valid data
        # Just mark as needing rebuild next time

    def _write_meta_atomic(self, path: Path, data: dict) -> None:
        """Write JSON atomically via temp file + rename."""
        tmp = path.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)

    def _acquire_build_lock(self):
        """Acquire non-blocking exclusive lock for build serialization."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        fd = open(self._lock_path, "w")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fd.close()
            raise RuntimeError(
                "Another ColBERT build is in progress. "
                "Wait for it to finish or remove .tldrs/index/plaid/.build.lock"
            )
        return fd

    def _release_build_lock(self, fd) -> None:
        if fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                fd.close()
            except Exception:
                pass
