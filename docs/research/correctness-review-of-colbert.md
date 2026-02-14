# Correctness Review: ColBERT Backend Implementation (commit 8aa1cc2)

**Reviewer:** Julik (Flux-drive Correctness Reviewer)
**Date:** 2026-02-14
**Scope:** Race conditions, data consistency, concurrency bugs in semantic search backend implementation

---

## Executive Summary

The ColBERT backend implementation has **13 correctness issues** ranging from P1 (data corruption) to P3 (minor race). The most critical problems are:

1. **P1**: Dual meta.json write race can corrupt backend detection
2. **P1**: Missing lock for concurrent search during rebuild causes stale reads
3. **P1**: PLAID centroid drift warning has no enforcement mechanism
4. **P2**: Backend cache invalidation race in daemon
5. **P2**: Sentinel cleanup race creates detection gap

The implementation uses file locks correctly for build serialization but lacks synchronization for concurrent read/write operations and has inconsistent metadata management.

---

## Data Integrity Findings

### P1-1: Dual meta.json Write Creates Backend-Detection Race

**Location:** `colbert_backend.py:302-316` (save method)

**Failure narrative:**

```python
# Process A: ColBERT backend saving index
colbert.save()
  self._write_meta_atomic(self._meta_path, meta_data)  # Writes .tldrs/index/plaid/meta.json
  # <-- Process B reads here
  self._write_meta_atomic(top_meta_path, top_meta)      # Writes .tldrs/index/meta.json

# Process B: Factory reading backend type
existing = _read_index_backend(project_path)  # Reads .tldrs/index/meta.json
# Returns None or stale "faiss" → wrong backend selected
```

**Interleaving timeline:**
```
T0: Process A starts save(), writes plaid/meta.json with backend="colbert"
T1: Process B calls get_backend("auto"), reads .tldrs/index/meta.json
T2: File doesn't exist yet or has old backend="faiss"
T3: Process B loads FAISSBackend
T4: Process A writes .tldrs/index/meta.json with backend="colbert"
T5: Process B searches with wrong backend → FileNotFoundError or stale results
```

**Root cause:** Two atomic writes with no transaction boundary. The top-level meta.json is the source of truth for backend detection, but it's written second without a lock.

**Fix:** Write top-level meta.json first (before PLAID meta), or introduce a two-phase commit with a `.meta.tmp` lock file that readers check.

**Minimal robust fix:**
```python
def save(self) -> None:
    # Write top-level meta FIRST (backend detection must never see partial state)
    top_meta = {
        "backend": "colbert",
        "version": "1.0",
        "embed_model": self.MODEL,
        "embed_backend": "colbert",
        "dimension": 48,
        "count": len(self._units),
    }
    top_meta_path = self._parent_meta_path
    top_meta_path.parent.mkdir(parents=True, exist_ok=True)
    self._write_meta_atomic(top_meta_path, top_meta)

    # Now safe to write PLAID-specific meta
    meta_data = {...}
    self._write_meta_atomic(self._meta_path, meta_data)
```

---

### P1-2: Missing Lock for Concurrent Search During Rebuild

**Location:** `colbert_backend.py:207-249` (search method)

**Failure narrative:**

```python
# Thread A: Building new index
build()
  lock_fd = self._acquire_build_lock()  # Holds .build.lock
  temp_dir.rename(self.index_dir)       # Atomic swap directory
  self._index = index                   # Update in-memory reference
  self._retriever = retrieve.ColBERT(index=self._index)  # <-- NOT ATOMIC

# Thread B: Searching (concurrent)
search(query, k=10)
  if self._retriever is None:
    self.load()  # Loads old index
  # <-- Directory swap happens here
  results = self._retriever.retrieve(query_embeddings, k=k)  # May read inconsistent state
```

**Interleaving timeline:**
```
T0: Thread A acquires build lock, builds in temp dir
T1: Thread B calls search(), self._retriever is not None (old index loaded)
T2: Thread A swaps directories: temp_dir.rename(self.index_dir)
T3: Thread A updates self._index (new index object)
T4: Thread B calls self._retriever.retrieve() on old retriever
T5: Old retriever's underlying PLAID index files are now in plaid-old/
T6: Thread B gets FileNotFoundError or stale results from moved files
```

**Root cause:** The `_build.lock` file lock only serializes build operations. It does NOT protect concurrent searches from seeing inconsistent in-memory state during index swap. The directory rename is atomic, but the subsequent `self._index` and `self._retriever` updates are NOT atomic with respect to concurrent search() calls.

**Why this wakes you at 3 AM:** A long-running search query that starts just before a rebuild finishes will try to read from files that were just moved to `plaid-old/`. PyLate's PLAID index keeps file descriptors open, so you get I/O errors mid-search.

**Fix:** Add a read-write lock (e.g., threading.RLock). Build holds write lock, search holds read lock. Or make search check a version counter and retry if it changed during retrieval.

**Minimal robust fix (version-counter approach):**
```python
class ColBERTBackend:
    def __init__(self, project_path: str):
        # ...
        self._version = 0  # Increment on every save()

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        max_retries = 3
        for attempt in range(max_retries):
            v_start = self._version
            if self._retriever is None:
                if not self.load():
                    return []
            try:
                results = self._retriever.retrieve(query_embeddings, k=k)
                if self._version == v_start:  # No rebuild during retrieval
                    return formatted_results
                else:
                    logger.debug(f"Rebuild detected during search, retry {attempt+1}")
                    continue
            except Exception as e:
                if self._version != v_start:
                    continue  # Retry on rebuild-related errors
                raise
        logger.warning("Search failed after retries due to concurrent rebuild")
        return []

    def save(self) -> None:
        # ...
        self._version += 1
```

---

### P1-3: PLAID Centroid Drift Warning Has No Enforcement

**Location:** `colbert_backend.py:160-165`

**Issue:** The code warns after 20 incremental updates but continues adding documents anyway. PLAID's centroid clustering degrades with each incremental add, but there's no forced rebuild threshold.

**Failure mode:** After 100+ incremental adds, retrieval quality silently degrades. Users see "why is search getting worse?" without any indication that index quality has drifted.

**Current behavior:**
```python
if self._incremental_updates >= 20 and not needs_full_rebuild:
    logger.warning("Index has %d incremental updates...", self._incremental_updates)
    # WARNING: Still proceeds with incremental add, not a rebuild
```

**Fix:** Introduce a hard limit (e.g., 50 incremental updates) that forces `needs_full_rebuild = True`. Log clearly that we're auto-rebuilding for quality.

**Minimal robust fix:**
```python
REBUILD_THRESHOLD_DELETES = 0.20
REBUILD_THRESHOLD_INCREMENTAL = 50  # Force rebuild after N incremental updates

if self._incremental_updates >= REBUILD_THRESHOLD_INCREMENTAL and not needs_full_rebuild:
    logger.info(
        "Index has %d incremental updates (>= threshold %d), forcing full rebuild for quality",
        self._incremental_updates, REBUILD_THRESHOLD_INCREMENTAL,
    )
    needs_full_rebuild = True
```

---

### P2-4: Backend Cache Invalidation Race in Daemon

**Location:** `daemon.py:605` (semantic index action)

**Failure narrative:**

```python
# Client A: Triggers semantic index rebuild
daemon._handle_semantic({"action": "index", "backend": "colbert"})
  build_index(...)  # Writes new index files to disk
  self._semantic_backend = None  # Invalidate cached backend

# Client B: Searches (concurrent, different socket connection)
daemon._handle_semantic({"action": "search", "query": "foo"})
  if not hasattr(self, "_semantic_backend") or self._semantic_backend is None:
    self._semantic_backend = get_backend(...)  # <-- Loads OLD index from disk
    self._semantic_backend.load()              # <-- Load() sees partial write
```

**Interleaving timeline:**
```
T0: Client A calls index action, daemon starts build_index()
T1: build_index() writes plaid/meta.json (new backend="colbert")
T2: Client B calls search action, checks self._semantic_backend (None)
T3: Client B calls get_backend(), reads .tldrs/index/meta.json (old or not yet written)
T4: Client B loads FAISSBackend, calls load() on faiss files
T5: Client A writes .tldrs/index/meta.json (backend="colbert")
T6: Client B returns FAISS results (wrong backend) or FileNotFoundError
T7: Client A sets self._semantic_backend = None (too late)
```

**Root cause:** The daemon invalidates `_semantic_backend` AFTER `build_index()` completes, but concurrent search requests can call `get_backend()` during the build and load stale index metadata.

**Why this fails:** `build_index()` is not atomic with cache invalidation. The dual meta.json write (P1-1) makes this worse.

**Fix:** Invalidate `_semantic_backend` BEFORE calling `build_index()`, and add a lock around the cache check-and-load in search.

**Minimal robust fix:**
```python
import threading

class TLDRDaemon:
    def __init__(self, project_path: Path):
        # ...
        self._semantic_lock = threading.RLock()

    def _handle_semantic(self, command: dict) -> dict:
        action = command.get("action", "search")

        if action == "index":
            from ..semantic.index import build_index
            language = command.get("language", "python")
            backend = command.get("backend", "auto")

            with self._semantic_lock:
                self._semantic_backend = None  # Invalidate FIRST

            stats = build_index(str(self.project), language=language, backend=backend)

            return {"status": "ok", "indexed": stats.total_units}

        elif action == "search":
            with self._semantic_lock:
                if not hasattr(self, "_semantic_backend") or self._semantic_backend is None:
                    from ..semantic.backend import get_backend
                    self._semantic_backend = get_backend(str(self.project))
                    self._semantic_backend.load()

                results = self._semantic_backend.search(query, k=k)
            # ... format results
```

---

### P2-5: Sentinel Cleanup Race Creates Detection Gap

**Location:** `colbert_backend.py:175, 201, 254-256`

**Failure narrative:**

```python
# Process A: Building index
build()
  self._sentinel_path.touch()  # .build_in_progress created
  # ... encoding, building ...
  self._sentinel_path.unlink(missing_ok=True)  # Removed on success

# Process B: Loading index (concurrent)
load()
  if self._sentinel_path.exists():  # <-- TOCTOU race
    self._cleanup_partial()
    return False
```

**Interleaving timeline:**
```
T0: Process A creates sentinel at start of build()
T1: Process B calls load(), checks sentinel (exists=True)
T2: Process A finishes build, unlinks sentinel
T3: Process B calls _cleanup_partial() (no-op, sentinel already gone)
T4: Process B returns False (refuses to load valid index)
T5: Next search gets empty results
```

**Root cause:** Time-of-check-time-of-use (TOCTOU) race between sentinel check and cleanup. The sentinel is removed before the in-memory state is updated, so concurrent load() can see a valid index but refuse to load it because the sentinel existed a moment ago.

**Why this is subtle:** The sentinel is meant to detect crashed builds, but the check happens OUTSIDE the build lock. A concurrent load() during the brief window between "build finishes" and "save() updates meta.json" will incorrectly reject the valid index.

**Fix:** Check sentinel while holding the build lock (requires making load() acquire a shared lock), or use a two-phase sentinel (`.building` → `.built`).

**Minimal robust fix (add load lock):**
```python
def load(self) -> bool:
    # Acquire shared lock to prevent TOCTOU with build's sentinel cleanup
    lock_fd = None
    try:
        lock_fd = open(self._lock_path, "r")
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_SH)  # Shared lock

        if self._sentinel_path.exists():
            logger.warning("Partial ColBERT build detected, needs rebuild")
            self._cleanup_partial()
            return False

        if not self._meta_path.exists():
            return False

        # ... rest of load logic ...
        return True

    finally:
        if lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()
```

---

### P2-6: Incremental Add Orphans Deleted IDs in PLAID Index

**Location:** `colbert_backend.py:405-409`

**Issue:** When `deleted_ids` exist but are below rebuild threshold (20%), they're removed from `_units` and `_unit_hashes` dicts but remain as stale entries in the PLAID index. PLAID has no delete API, so these orphaned document IDs stay in the index forever.

**Failure mode:**
```python
# Build 1: Index 100 documents (IDs 0-99)
build(units_0_to_99, ...)

# Build 2: 10 documents deleted, 90 remain (10% deletion ratio < 20%)
build(units_0_to_89, ...)
  deleted_ids = {90, 91, ..., 99}
  # Incremental path taken (no rebuild)
  for uid in deleted_ids:
      self._units.pop(uid, None)       # Removed from dict
      self._unit_hashes.pop(uid, None)  # Removed from dict
  # BUT: IDs 90-99 still exist in PLAID index as searchable documents
```

**Consequence:** Search results include deleted/stale documents. Mapping `doc_id` back to `self._units` returns None (line 238), so the result is silently dropped. This is safe (no corruption) but wasteful and confusing.

**Correctness impact:** **Medium**. Results are filtered at query time (no stale data returned), but the index grows unbounded with garbage until a rebuild. After 10 incremental deletes, index size is 10% larger than necessary.

**Fix:** Track cumulative deletion ratio since last rebuild, not just current batch. Force rebuild when cumulative deletions exceed threshold.

**Minimal robust fix:**
```python
class ColBERTBackend:
    def __init__(self, project_path: str):
        # ...
        self._deleted_since_rebuild = 0  # Cumulative deletions

    def build(self, units, texts, *, rebuild=False) -> BackendStats:
        # ...
        deleted_ids = existing_ids - set(incoming.keys())
        self._deleted_since_rebuild += len(deleted_ids)

        if self._deleted_since_rebuild > 0 and not needs_full_rebuild:
            total_docs = len(existing_ids)
            cumulative_ratio = self._deleted_since_rebuild / max(total_docs, 1)
            if cumulative_ratio >= self.REBUILD_THRESHOLD:
                logger.info(
                    "Cumulative deletions %d / %d (%.1f%%) >= threshold, triggering rebuild",
                    self._deleted_since_rebuild, total_docs, cumulative_ratio * 100,
                )
                needs_full_rebuild = True

        if needs_full_rebuild:
            self._deleted_since_rebuild = 0  # Reset counter
```

---

## Concurrency Findings

### P1-7: No Synchronization Between FAISS Build and Search

**Location:** `faiss_backend.py:405-445` (search method)

**Issue:** Same class of bug as P1-2, but for FAISS backend. The `build()` method holds `_build.lock` file lock, but `search()` reads `self._faiss_index` and `self._units` without any lock.

**Failure narrative:**

```python
# Thread A: Building incremental update
build(new_units, new_texts)
  lock_fd = self._acquire_build_lock()
  # ... compute embeddings ...
  self._faiss_index.add(matrix)  # Modifies in-memory FAISS index
  self._units = all_units         # Replaces list (NOT ATOMIC)
  self._release_build_lock(lock_fd)

# Thread B: Searching (concurrent)
search(query, k=10)
  if self._faiss_index is None:  # False, index already loaded
    return []
  # <-- Thread A updates self._units here
  scores, indices = self._faiss_index.search(query_arr, k)  # Returns indices [0,1,2,...]
  for idx in indices[0]:
    self._units[idx]  # <-- IndexError if list was replaced mid-search
```

**Interleaving timeline:**
```
T0: Thread A loads existing index (10 units)
T1: Thread B calls search(), checks self._faiss_index (not None)
T2: Thread A adds 5 new units, rebuilds FAISS index (now 15 units)
T3: Thread A assigns self._units = all_units (list of 15 CodeUnit objects)
T4: Thread B calls self._faiss_index.search() on NEW index (15 vectors)
T5: FAISS returns indices [10, 11, 12] (valid for new index)
T6: Thread B loops: for idx in [10, 11, 12]: self._units[idx]
T7: If Thread B still sees OLD list (10 units), IndexError on idx=10
```

**Root cause:** `self._units` and `self._faiss_index` are updated separately, not atomically. File lock doesn't help because search doesn't acquire it.

**Fix:** Use a threading.RLock, or make search reload if index pointer changed.

**Minimal robust fix (add instance lock):**
```python
import threading

class FAISSBackend:
    def __init__(self, project_path, embed_backend="auto", embed_model=None):
        # ...
        self._instance_lock = threading.RLock()

    def build(self, units, texts, *, rebuild=False) -> BackendStats:
        lock_fd = self._acquire_build_lock()
        try:
            # ... build logic ...
            with self._instance_lock:
                self._faiss_index = faiss.IndexFlatIP(dimension)
                self._faiss_index.add(matrix)
                self._units = all_units
                self._id_to_idx = {u.id: i for i, u in enumerate(self._units)}
        finally:
            self._release_build_lock(lock_fd)

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        with self._instance_lock:
            if self._faiss_index is None or not self._units:
                return []
            # ... rest of search logic ...
```

---

### P2-8: BM25 Index Rebuild Race in `_build_bm25`

**Location:** `index.py:392-414` (\_build_bm25 function)

**Issue:** The BM25Store build/save happens AFTER the main backend's save() completes. If two concurrent builds run (unlikely due to build lock, but possible via daemon restart), they can clobber each other's BM25 files.

**Failure narrative:**

```python
# Process A: tldrs semantic index --backend=colbert
build_index(...)
  backend.build(units, texts)
  backend.save()  # Writes PLAID index + meta.json
  _build_bm25(backend, units, texts)  # <-- NO LOCK
    bm25.build(all_ids, texts)
    bm25.save()  # Writes .tldrs/index/bm25_index.pkl

# Process B: tldrs semantic index --backend=faiss (concurrent)
build_index(...)
  backend.build(units, texts)  # Blocked by _build.lock
  # ... waits ...
  backend.save()
  _build_bm25(backend, units, texts)  # <-- NO LOCK, runs concurrently with A
    bm25.build(all_ids, texts)
    bm25.save()  # Overwrites .tldrs/index/bm25_index.pkl
```

**Root cause:** `_build_bm25` runs outside the main backend's build lock. If two backends coexist (e.g., rebuilding from FAISS to ColBERT), their BM25 builds can race.

**Correctness impact:** **Low**. BM25 is optional (graceful fallback), and both builds produce valid output. Last-writer-wins semantics mean one BM25 index gets clobbered, but it's regenerated next build.

**Fix:** Acquire the backend's build lock again before calling `_build_bm25`, or make BM25Store use its own lock file.

**Minimal robust fix:**
```python
def _build_bm25(search_backend, units, texts, show_progress=False):
    from .bm25_store import BM25Store
    bi = search_backend.info()
    bm25_dir = Path(bi.index_path)
    if bi.backend_name == "colbert":
        bm25_dir = bm25_dir.parent

    bm25 = BM25Store(bm25_dir)

    # Re-acquire build lock to prevent concurrent BM25 builds
    lock_path = bm25_dir / ".build.lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        bm25.build([u.id for u in units], texts)
        bm25.save()
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
```

---

### P3-9: Daemon `_handle_semantic` Lacks Timeout on build_index

**Location:** `daemon.py:598-606`

**Issue:** The daemon calls `build_index()` synchronously in the main request-handling thread. If a client triggers a semantic index rebuild (which can take 10+ minutes on large codebases), the daemon is blocked and can't respond to other requests.

**Failure mode:** Client A rebuilds index on 100k-file codebase. Client B tries to ping daemon → timeout. Client B thinks daemon is dead, kills and restarts it, which kills Client A's rebuild mid-flight.

**Fix:** Run `build_index()` in a background thread or subprocess, return immediately with a "rebuild started" response.

**Minimal robust fix:**
```python
def _handle_semantic(self, command: dict) -> dict:
    action = command.get("action", "search")

    if action == "index":
        if hasattr(self, "_semantic_rebuild_in_progress") and self._semantic_rebuild_in_progress:
            return {"status": "ok", "message": "Rebuild already in progress"}

        self._semantic_rebuild_in_progress = True

        def do_rebuild():
            try:
                from ..semantic.index import build_index
                language = command.get("language", "python")
                backend = command.get("backend", "auto")
                build_index(str(self.project), language=language, backend=backend)
                with self._semantic_lock:
                    self._semantic_backend = None
            finally:
                self._semantic_rebuild_in_progress = False

        import threading
        thread = threading.Thread(target=do_rebuild, daemon=True)
        thread.start()

        return {"status": "ok", "message": "Semantic index rebuild started in background"}
```

---

### P3-10: `_write_meta_atomic` PID-Based Tempfile Collision

**Location:** `colbert_backend.py:419-423`, `faiss_backend.py:559-563`

**Issue:** Both backends use `os.getpid()` for atomic write tempfile naming:

```python
tmp = path.with_suffix(f".tmp.{os.getpid()}")
tmp.write_text(json.dumps(data, indent=2))
tmp.replace(path)
```

If two threads in the SAME process call `save()` concurrently (e.g., daemon serving two clients), they use the same PID and clobber each other's tempfile.

**Failure narrative:**

```python
# Thread A: Saving FAISS backend
faiss_backend.save()
  tmp = meta_path.with_suffix(".tmp.12345")  # PID=12345
  tmp.write_text(json.dumps(meta_data_A))
  # <-- Thread B runs here
  tmp.replace(meta_path)

# Thread B: Saving ColBERT backend (same process)
colbert_backend.save()
  tmp = meta_path.with_suffix(".tmp.12345")  # SAME PID
  tmp.write_text(json.dumps(meta_data_B))  # Overwrites Thread A's tempfile
  tmp.replace(meta_path)  # Replaces with Thread B's data
```

**Interleaving timeline:**
```
T0: Thread A writes .tldrs/index/meta.json.tmp.12345 (FAISS metadata)
T1: Thread B writes .tldrs/index/meta.json.tmp.12345 (ColBERT metadata, overwrites)
T2: Thread A calls tmp.replace() → renames ColBERT data to meta.json (WRONG)
T3: Thread B calls tmp.replace() → FileNotFoundError (tmp already moved)
```

**Correctness impact:** **Low** in practice (daemon typically doesn't save two backends simultaneously), but dangerous for multi-threaded CLI use.

**Fix:** Use `threading.get_ident()` or `uuid.uuid4()` for tempfile suffix.

**Minimal robust fix:**
```python
import uuid

def _write_meta_atomic(self, path: Path, data: dict) -> None:
    tmp = path.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)
```

---

## Error Recovery & Partial Failure

### P2-11: `_build_fresh_index` Leaves plaid-old on Exception

**Location:** `colbert_backend.py:372-376`

**Issue:** If an exception occurs after the atomic swap (line 357: `temp_dir.rename(self.index_dir)`), the cleanup of `plaid-old` (line 360) is skipped because the exception handler (line 372-376) only cleans up `temp_dir`.

**Failure mode:**

```python
_build_fresh_index(...)
  temp_dir.rename(self.index_dir)  # Swap completes
  self.index_dir.rename(old_dir)   # Old index moved to plaid-old
  # <-- EXCEPTION HERE (e.g., OOM during retriever init)
  self._retriever = retrieve.ColBERT(index=self._index)  # Fails
except Exception:
  if temp_dir.exists():  # False, already renamed
    shutil.rmtree(temp_dir)
  raise  # plaid-old/ left behind
```

**Consequence:** After a failed rebuild, `plaid-old/` directory remains. Next rebuild creates a new `plaid-old-{pid}/` or fails to rename. Disk fills with orphaned old indexes.

**Fix:** Always clean up `plaid-old` in finally block, not just on success.

**Minimal robust fix:**
```python
def _build_fresh_index(self, indexes_mod, ids, embeddings, incoming):
    temp_dir = self.index_dir.parent / f"plaid-build-{os.getpid()}"
    old_dir = self.index_dir.parent / "plaid-old"

    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        # ... build in temp_dir ...
        # Atomic swap
        if self.index_dir.exists():
            if old_dir.exists():
                shutil.rmtree(old_dir)
            self.index_dir.rename(old_dir)
        temp_dir.rename(self.index_dir)

        # Update state (can fail)
        self._units = {uid: incoming[uid][0] for uid in ids}
        self._unit_hashes = {uid: incoming[uid][0].file_hash for uid in ids}
        from pylate import retrieve
        self._index = index
        self._retriever = retrieve.ColBERT(index=self._index)

    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        # Always clean up old dir on success or failure
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)
```

---

### P3-12: FAISS `_reconstruct_all_vectors` Silent Fallback Hides Corruption

**Location:** `faiss_backend.py:517-527`

**Issue:** If bulk reconstruction fails, code falls back to per-vector loop without logging the reason. A partially corrupted index can return wrong vectors without any warning.

```python
try:
    return self._faiss_index.reconstruct_n(0, len(self._units))
except Exception:  # <-- Swallows ALL exceptions
    vectors = []
    for i in range(len(self._units)):
        vectors.append(self._faiss_index.reconstruct(i))
    return np.vstack(vectors).astype(np.float32)
```

**Failure mode:** Index has 1000 vectors, but internal FAISS state is corrupted (e.g., partial write during crash). `reconstruct_n()` throws an internal FAISS error. Code silently switches to per-vector reconstruction, which may return garbage or trigger secondary errors.

**Fix:** Log the exception before fallback, and consider failing fast if bulk reconstruction fails.

**Minimal robust fix:**
```python
try:
    return self._faiss_index.reconstruct_n(0, len(self._units))
except Exception as e:
    logger.warning(
        "Bulk vector reconstruction failed (%s), falling back to per-vector (slow). "
        "Index may be corrupted, consider rebuilding.",
        e
    )
    vectors = []
    for i in range(len(self._units)):
        try:
            vectors.append(self._faiss_index.reconstruct(i))
        except Exception as vec_err:
            logger.error(f"Failed to reconstruct vector {i}: {vec_err}")
            raise  # Fail fast on per-vector error
    return np.vstack(vectors).astype(np.float32)
```

---

### P3-13: `_incremental_add` Doesn't Validate embeddings Length

**Location:** `colbert_backend.py:393-397`

**Issue:** If encoding fails or returns wrong-length embeddings, `add_documents()` is called with mismatched IDs and embeddings. PLAID may crash or silently index garbage.

```python
def _incremental_add(self, indexes_mod, ids_to_encode, embeddings, incoming, ...):
    if ids_to_encode and embeddings is not None:
        self._index.add_documents(
            documents_ids=ids_to_encode,
            documents_embeddings=embeddings,
        )
```

**Failure mode:** Encoding 10 documents but encoder only returns 8 embeddings (e.g., timeout, OOM). PLAID associates wrong embeddings with IDs, or crashes with dimension mismatch.

**Fix:** Assert `len(ids_to_encode) == len(embeddings)` before calling `add_documents()`.

**Minimal robust fix:**
```python
if ids_to_encode and embeddings is not None:
    if len(ids_to_encode) != len(embeddings):
        raise RuntimeError(
            f"Embedding count mismatch: {len(ids_to_encode)} IDs, "
            f"{len(embeddings)} embeddings. Incremental add aborted."
        )
    self._index.add_documents(
        documents_ids=ids_to_encode,
        documents_embeddings=embeddings,
    )
```

---

## Shutdown & Cleanup

**No major issues.** The sentinel cleanup is non-destructive (P2-5 is detection, not cleanup). File locks are properly released in `finally` blocks. Daemon shutdown correctly closes sockets and removes PID files.

---

## Testing Recommendations

### Race condition tests (require concurrent execution):

1. **Dual meta.json write race (P1-1):** Spawn two threads, one calls `save()`, other calls `get_backend("auto")` in a tight loop. Assert backend type never changes mid-flight.

2. **Concurrent search during rebuild (P1-2):** Thread A rebuilds index, Thread B searches in a loop. Assert no FileNotFoundError, no IndexError.

3. **Backend cache invalidation (P2-4):** Daemon handles concurrent `index` and `search` actions from two clients. Assert search never returns wrong backend.

4. **FAISS build/search race (P1-7):** Same as P1-2 but for FAISS backend.

### Deterministic correctness tests:

1. **Incremental delete orphan tracking (P2-6):** Build 100 docs, delete 10, build again. Assert `_deleted_since_rebuild` increments. Delete 10 more, assert rebuild triggered.

2. **PLAID centroid drift enforcement (P1-3):** Do 50 incremental adds, assert 51st triggers rebuild.

3. **Partial build cleanup (P2-11):** Mock exception during `_build_fresh_index` after swap. Assert `plaid-old/` is removed.

4. **Embeddings length mismatch (P3-13):** Mock encoder to return 8 embeddings for 10 IDs. Assert RuntimeError.

---

## Prioritization Summary

**Fix immediately (P1):**
- P1-1: Dual meta.json write race (data corruption)
- P1-2: Concurrent search during rebuild (stale reads, I/O errors)
- P1-3: PLAID centroid drift enforcement (silent quality degradation)
- P1-7: FAISS build/search race (IndexError crashes)

**Fix before production (P2):**
- P2-4: Backend cache invalidation race
- P2-5: Sentinel cleanup TOCTOU
- P2-6: Incremental delete orphan tracking
- P2-8: BM25 rebuild race
- P2-11: plaid-old cleanup on exception

**Fix when convenient (P3):**
- P3-9: Daemon build timeout
- P3-10: PID-based tempfile collision
- P3-12: Silent fallback in vector reconstruction
- P3-13: Embeddings length validation

---

## Appendix: Invariants to Maintain

1. **Backend detection invariant:** `_read_index_backend()` must always return the active backend type. Violated by P1-1.

2. **Index consistency invariant:** For any loaded backend, `len(self._units) == index.ntotal` (FAISS) or `len(self._units) == len(indexed_doc_ids)` (PLAID). Violated by P1-7 during concurrent update.

3. **Sentinel integrity invariant:** If `.build_in_progress` exists, no valid index exists. Violated by P2-5 TOCTOU.

4. **Atomicity invariant:** Backend state changes (index swap, metadata write, in-memory update) must be atomic with respect to concurrent readers. Violated by P1-2, P1-7.

5. **Deletion tracking invariant:** Cumulative deletions since last rebuild must trigger rebuild at threshold. Not enforced (P2-6).

6. **Quality invariant:** Index retrieval quality must not silently degrade. Violated by P1-3 (no enforcement of incremental update limit).

---

**End of review.** All findings are actionable with minimal code changes. Most critical issues (P1) can be fixed with lock additions and write-order changes. The architecture is sound; execution has concurrency gaps.
