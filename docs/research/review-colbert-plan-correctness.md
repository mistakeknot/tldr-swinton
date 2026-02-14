# Correctness Review: ColBERT Search Backend Implementation Plan

**Reviewer:** Julik (Flux-drive Correctness Reviewer)
**Date:** 2026-02-14
**Plan:** `docs/plans/2026-02-14-colbert-search-backend.md`

---

## Executive Summary

The plan introduces a ColBERT backend with incremental updates but has **four critical correctness failures** related to concurrent access during rebuilds, partial-write inconsistency between meta.json and PLAID index, interrupt safety, and a TOCTOU race in the rebuild threshold check. All issues have production impact: stale reads, query failures, corrupted indexes, or silent drift. Mitigations are provided below.

---

## Critical Failures

### 1. Concurrent Search During Index Rebuild (Race Condition)

**Failure Narrative:**

The daemon caches a `ColBERTBackend` instance at `self._semantic_backend` (Step 5, daemon.py lines 225-228). The backend holds `self._index`, `self._retriever`, and `self._units` as in-process state.

Timeline of a race:
1. **T0:** User runs `tldrs semantic search "auth"` → daemon loads backend, sets `self._semantic_backend` to the ColBERTBackend instance with PLAID index A (10,000 docs).
2. **T1:** User modifies 3,000 files (~25% of the corpus), triggering the 20% deletion threshold.
3. **T2:** `build()` is called (via CLI or daemon) → starts full rebuild.
4. **T3:** During rebuild, `build()` calls `index.add_documents(...)` to create a fresh PLAID index B (empty initially, grows as docs are added).
5. **T4:** **Concurrent search request arrives** → daemon's cached `self._semantic_backend` still points to the **old index A** on disk, but the rebuild has already started writing to the same directory.
6. **T5:** PLAID's `add_documents()` writes new centroid files and metadata to `.tldrs/index/plaid/`. The old retriever's memory-mapped files are now stale or partially overwritten.
7. **T6:** Search reads from index A's retriever while index B's files are being written → **segfault, corrupted results, or KeyError** (doc IDs in new index don't match old `self._units` map).
8. **T7:** Rebuild completes, updates `meta.json` → `self._units` is replaced. Future searches now map PLAID doc IDs to the wrong `CodeUnit` objects if the daemon didn't reload.

**Root Cause:** The plan does not specify how `build()` and `search()` synchronize access to the shared PLAID index directory. PLAID's `add_documents()` is not atomic — it writes centroids, metadata, and inverted lists progressively. The daemon's cached backend instance assumes the index is stable.

**Impact:** Production searches during rebuild will fail with `FileNotFoundError` (missing centroid files), return garbage results (doc ID mismatch), or crash (mmap corruption).

**Mitigation:**

- **Use atomic index swap via temp directory + rename:**
  ```python
  def build(self, units, texts, *, rebuild=False):
      if rebuild or self._needs_rebuild(units):
          # Write to temp dir
          temp_dir = self.index_dir.parent / f"plaid-{os.getpid()}"
          # ... build PLAID index in temp_dir ...
          # Atomic swap
          old_dir = self.index_dir.parent / "plaid-old"
          self.index_dir.rename(old_dir)
          temp_dir.rename(self.index_dir)
          old_dir.rmtree()  # Clean up after rename
  ```

- **Daemon: reload backend after build completes:**
  ```python
  def _handle_semantic(self, command):
      action = command.get("action")
      if action == "index":
          # ... call build_index() ...
          # Invalidate cached backend so next search reloads
          self._semantic_backend = None
  ```

- **Add a read-write lock** if atomic swap is impractical (but this serializes searches during rebuild, defeating the daemon's purpose).

---

### 2. Partial-Write Inconsistency: meta.json vs PLAID Index

**Failure Narrative:**

The plan stores two pieces of state:
- `meta.json` — unit list + file hashes + backend metadata (written by `save()`)
- PLAID index — centroids + inverted lists + PLAID metadata (written by `index.add_documents()` or `retriever.index()`)

Timeline of a crash:
1. **T0:** `build()` starts full rebuild with 5,000 units.
2. **T1:** `index.add_documents(ids, embeddings)` completes → PLAID index written to disk (5,000 docs).
3. **T2:** `save()` starts writing `meta.json` with updated unit list.
4. **T3:** **Process killed** (OOM, SIGKILL, power loss) after `meta.json` is opened but before `write()` completes.
5. **T4:** On restart, `load()` reads **stale meta.json** with 4,000 units, but PLAID index has 5,000 docs.
6. **T5:** Search returns PLAID doc ID 4,500 → `self._units[4500]` → **IndexError**.

**Root Cause:** The plan does not define an atomic commit protocol for the two persistence layers. `meta.json` is a separate file from PLAID's index, and Python's `write_text()` is not crash-safe (data may not be flushed to disk before crash).

**Impact:** After a crash during rebuild, the index is in a split-brain state: PLAID thinks it has N docs, meta.json thinks it has M < N. All searches fail with IndexError until manual rebuild.

**Mitigation:**

- **Write meta.json atomically via temp file + rename:**
  ```python
  def save(self):
      self.index_dir.mkdir(parents=True, exist_ok=True)
      # ... PLAID index is already persisted by PyLate ...
      # Atomic meta.json write
      meta_data = {
          "units": [u.to_dict() for u in self._units],
          "hashes": self._unit_hashes,
          "backend": "colbert",
          "model": self.MODEL,
      }
      temp_meta = self.index_dir / f"meta.json.tmp.{os.getpid()}"
      temp_meta.write_text(json.dumps(meta_data, indent=2))
      temp_meta.replace(self.index_dir / "meta.json")
  ```

- **Add a version/checksum field** to detect mismatches:
  ```python
  meta_data["plaid_doc_count"] = len(self._units)
  # On load:
  if meta["plaid_doc_count"] != len(self._index.docids):
      raise CorruptedIndexError("Rebuild required")
  ```

- **Require fsync** if crash-safety is critical (but slows down builds):
  ```python
  fd = os.open(temp_meta, os.O_WRONLY)
  os.fsync(fd)
  os.close(fd)
  ```

---

### 3. Interrupted Build Leaves Partial PLAID Index

**Failure Narrative:**

Timeline of an interrupt:
1. **T0:** `build()` starts full rebuild with 10,000 units.
2. **T1:** Encodes first 5,000 units (~3 minutes on CPU PyLate).
3. **T2:** Calls `index.add_documents(ids[:5000], embeddings[:5000])` → PLAID writes partial centroids.
4. **T3:** **User hits Ctrl+C** or process is killed.
5. **T4:** PLAID index dir contains **partial centroids and metadata** (5,000 docs).
6. **T5:** `meta.json` was never written (only written at the end in `save()`).
7. **T6:** On restart, `load()` finds no `meta.json` → treats index as non-existent.
8. **T7:** User runs search → "No index found. Run `tldrs index` first."
9. **T8:** User runs `tldrs index` → `load()` returns False (no meta.json), but **PLAID index dir is not empty**.
10. **T9:** `build()` tries to create fresh index in same dir → PLAID errors or silently merges with stale partial data.

**Root Cause:** The plan does not specify cleanup of partial PLAID state when `save()` never completes. PLAID's `add_documents()` is incremental and side-effectful — it writes to disk immediately, not transactionally.

**Impact:** After interrupt, the index is in a zombie state: PLAID files exist but are incomplete, and the system doesn't know whether to resume or rebuild. Subsequent builds may silently corrupt by merging new data with stale partial centroids.

**Mitigation:**

- **Write sentinel file to mark "build in progress":**
  ```python
  def build(self, units, texts, *, rebuild=False):
      in_progress = self.index_dir / ".build_in_progress"
      in_progress.touch()
      try:
          # ... encode, add_documents, etc. ...
          self.save()
      finally:
          in_progress.unlink(missing_ok=True)

  def load(self):
      in_progress = self.index_dir / ".build_in_progress"
      if in_progress.exists():
          logger.warning("Partial build detected, forcing full rebuild")
          self.clear()  # Delete PLAID dir
          return False
      # ... normal load ...
  ```

- **Alternative: always write to temp dir, only rename on success** (same as mitigation #1).

---

### 4. TOCTOU Race in Rebuild Threshold Check

**Failure Narrative:**

The plan computes the deletion threshold in `build()`:
```python
deletions = len(deleted_units)
if deletions > REBUILD_THRESHOLD * total → full rebuild
else → incremental add_documents()
```

Timeline of a race:
1. **T0:** Two `build()` calls start concurrently (e.g., CLI + daemon auto-reindex).
2. **T1:** Both load existing index with 1,000 units.
3. **T2:** Both compare units: 150 deletions (15% < 20% threshold) → **both choose incremental**.
4. **T3:** Both call `index.add_documents(new_embeddings)` on the same PLAID index dir.
5. **T4:** PLAID's `add_documents()` is **not thread-safe** → centroids are corrupted or doc IDs collide.
6. **T5:** Both write `meta.json` → **last writer wins**, but meta.json now references units from only one of the two builds.
7. **T6:** Index is silently corrupted: meta.json unit count doesn't match PLAID doc count, or doc IDs map to wrong units.

**Root Cause:** The threshold check is a **check-then-act** pattern with no synchronization. The plan does not specify mutual exclusion for concurrent `build()` calls.

**Impact:** If CLI `tldrs index` and daemon auto-reindex run concurrently, or if two users run `tldrs index` in the same workspace via tmux, the index is silently corrupted. Searches return wrong results or crash.

**Mitigation:**

- **Use a lock file to serialize builds:**
  ```python
  import fcntl

  def build(self, units, texts, *, rebuild=False):
      lock_file = self.index_dir / ".build.lock"
      self.index_dir.mkdir(parents=True, exist_ok=True)
      with open(lock_file, "w") as f:
          try:
              fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
          except BlockingIOError:
              raise RuntimeError("Another build is in progress")
          # ... rest of build logic ...
  ```

- **Daemon: check lock before auto-reindex:**
  ```python
  def _trigger_background_reindex(self):
      lock_file = self.project / ".tldrs/index/plaid/.build.lock"
      if lock_file.exists():
          logger.info("Build already in progress, skipping auto-reindex")
          return
      # ... spawn background build ...
  ```

---

## Edge Cases

### 5. Rebuild Threshold Edge Case: Exactly 20% Deletions

The plan uses `deletions > REBUILD_THRESHOLD * total`, which means **20.0%** deletions do NOT trigger rebuild (only 20.01%+). This is inconsistent with the documented threshold of "20% deletions."

**Fix:** Use `>=` instead of `>`:
```python
if deletions >= REBUILD_THRESHOLD * total:
```

**Alternative:** Document the off-by-one behavior explicitly ("rebuilds when >20%, not ≥20%").

---

### 6. Hash Collision in Unit IDs

The plan reuses `make_unit_id(file, name, line)` from FAISSBackend, which computes SHA256(f"{file}:{name}:{line}")[:16]. This is a **64-bit hash**, susceptible to birthday paradox collisions at ~4 billion units.

**Probability:** For a 10,000-unit project, collision probability is negligible (< 10^-9). For a 100,000-unit monorepo, it's ~0.001% per build.

**Impact if collision occurs:** Two units map to the same ID → one overwrites the other in `self._units` dict → one unit becomes unsearchable.

**Mitigation:** The 64-bit hash is already reasonable for code search. If this becomes a problem, switch to full SHA256 (32 hex chars) or add a collision check in `build()`.

---

### 7. Daemon Model Preload Timing

Step 5 suggests caching the PyLate model in the daemon's `_semantic_backend` for ~17s cold start. The plan doesn't specify **when** the model is loaded — on first search, or eagerly at daemon startup?

**Current plan (lazy load):** Model loads on first search → first query takes 17s, subsequent queries take 6ms.

**Impact:** User perception of "daemon is broken" if first query hangs for 17s with no feedback.

**Mitigation:**

- **Eager load on daemon start** (setup.sh or daemon init):
  ```python
  def __init__(self, project_path):
      # ... existing init ...
      if self._semantic_config.get("enabled"):
          self._ensure_semantic_backend()
  ```

- **Or add progress indicator** if lazy-loading:
  ```python
  def _ensure_model(self):
      if self._model is None:
          logger.info("Loading PyLate model (this may take ~15s)...")
          self._model = models.ColBERT(...)
  ```

---

## Data Integrity

### 8. Incremental Add with Centroid Drift

PLAID's docs warn: "Adding documents to an existing index may cause centroid drift, reducing retrieval quality over time."

The plan uses `index.add_documents()` for incremental updates but provides no mechanism to **detect or measure** centroid drift. Users won't know when retrieval quality has degraded until search results become obviously wrong.

**Impact:** After 50+ incremental updates, retrieval quality degrades silently. Users don't realize they need to rebuild.

**Mitigation:**

- **Track incremental-add count** in meta.json:
  ```python
  meta_data["incremental_updates_since_rebuild"] = self._update_count
  # Warn at 20 updates:
  if self._update_count >= 20:
      logger.warning("Index has been incrementally updated 20 times. "
                     "Consider a full rebuild for best quality.")
  ```

- **Add `tldrs semantic rebuild` command** to force rebuild without waiting for 20% deletions.

---

### 9. File Hash Change Detection Is Coarse-Grained

The plan uses `get_file_hash(file_path)` (SHA256 of entire file) to detect changes. This means:
- **Any edit** to a file re-embeds **all units** in that file (functions, classes, methods).
- If a 1,000-line file has 50 functions, editing one docstring re-embeds all 50.

**Impact:** Incremental builds are less efficient than they could be. For a large monorepo, this may push over the 20% deletion threshold unnecessarily (e.g., editing 200 files with 10 functions each = 2,000 units re-embedded, even if only 200 lines changed).

**Mitigation (future optimization):**

- **Per-unit hash** instead of per-file hash:
  ```python
  unit.content_hash = hashlib.sha256(unit.signature.encode() + unit.code.encode()).hexdigest()[:16]
  ```
  This requires storing unit code in memory during indexing, which the current plan avoids.

**Acceptable for MVP:** The coarse-grained approach is reasonable. Document this behavior in AGENTS.md so users understand why editing a single docstring re-indexes the whole file.

---

### 10. No Verification of PLAID Doc ID Stability

The plan assumes PLAID assigns doc IDs sequentially (0, 1, 2, ...) matching the order of `units` passed to `add_documents()`. If PLAID reorders docs internally, `self._units[doc_id]` will return the wrong unit.

**Verification needed:**
```python
# After add_documents:
assert len(self._index.docids) == len(self._units)
for i, doc_id in enumerate(self._index.docids):
    assert doc_id == ids[i], f"PLAID reordered docs: expected {ids[i]}, got {doc_id}"
```

**Likelihood of failure:** Low (PLAID preserves insertion order in practice), but not documented.

**Mitigation:** Add assertion in `build()` and log a warning if order doesn't match.

---

## Concurrency Summary

| Scenario | Race Class | Impact | Mitigation |
|----------|-----------|--------|-----------|
| Search during rebuild | Shared mutable state (PLAID index dir) | Segfault, corrupted results, doc ID mismatch | Atomic index swap via temp dir + daemon reload |
| Concurrent builds | TOCTOU (threshold check) | Silently corrupted index, doc ID collisions | Lock file (fcntl.LOCK_EX) |
| Crash during build | Partial write (meta.json vs PLAID) | IndexError on search, zombie index state | Atomic meta.json write + sentinel file |
| Interrupt during build | Resource leak (partial PLAID index) | Stale centroids merged with new data | `.build_in_progress` sentinel + cleanup |
| Daemon model preload | None (single-threaded daemon) | First query hangs 17s | Eager load + progress log |

---

## Recommendations

### Must-Fix Before Merge (Blocking)

1. **Atomic index swap** for concurrent search during rebuild (see mitigation #1).
2. **Atomic meta.json write** with temp file + rename (see mitigation #2).
3. **Sentinel file** for partial build cleanup (see mitigation #3).
4. **Lock file** to prevent concurrent builds (see mitigation #4).

### Should-Fix Before Production

5. Fix rebuild threshold off-by-one (`>=` not `>`).
6. Eager-load PyLate model in daemon or add progress log for first query.
7. Track incremental-update count, warn at 20 updates.

### Nice-to-Have (Post-MVP)

8. Per-unit hash for finer-grained incremental updates.
9. PLAID doc ID order assertion.
10. Centroid drift detection/measurement.

---

## Test Coverage Required

The plan's "Testing Strategy" section is incomplete. Add:

1. **Concurrent search during rebuild:** Spawn search thread, trigger rebuild, verify no crashes/stale results.
2. **Crash during build:** Kill process during `build()`, verify `load()` rejects partial index.
3. **Concurrent builds:** Run two `build()` calls in parallel, verify lock prevents corruption.
4. **Interrupt during build:** Send SIGINT during `build()`, verify cleanup removes partial PLAID index.
5. **Incremental-add correctness:** Add 100 units, search, verify all 100 are retrievable.
6. **Deletion threshold boundary:** Delete exactly 20% of units, verify rebuild triggers (or doesn't, if off-by-one is kept).

---

## Conclusion

The plan is architecturally sound but has **four critical concurrency/consistency failures** that will cause production outages. All are fixable with standard techniques (atomic swap, lock files, sentinel files). The incremental-update logic is correct given PLAID's constraints, but centroid drift and coarse-grained file hashing may degrade quality over time — acceptable for MVP, requires monitoring post-launch.

**Recommendation:** Implement mitigations 1-4 before merge. Ship with warnings for #6 and #7. Defer #8-10 to post-MVP observability improvements.
