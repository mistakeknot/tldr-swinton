# Architecture Review: ColBERT Backend Implementation (Commit 8aa1cc2)

**Reviewer**: Flux-drive Architecture & Design Reviewer
**Date**: 2026-02-14
**Scope**: Multi-backend semantic search refactor (FAISS + ColBERT)

## Executive Summary

This refactor successfully extracts a clean backend abstraction (`SearchBackend` protocol) and consolidates two independent search implementations (FAISS, ColBERT) under a unified interface. The design shows strong architectural discipline: clear boundaries, minimal coupling, and deliberate simplification through consolidation.

**Key Strengths:**
- Clean protocol-based abstraction with factory selection
- Backend-local embedding (no shared global state)
- Effective shim strategy preserves backward compatibility
- Daemon-layer caching keeps expensive models resident

**Areas for Improvement (P2/P3):**
- Minor duplication in locking/metadata patterns (acceptable trade-off)
- Identifier fast-path logic coupled to backend internals
- BM25 directory resolution has backend-specific knowledge

**Overall Assessment**: This is a textbook example of good refactoring. The boundaries are correct, the coupling is intentional and documented, and the complexity reduction (4 modules → 3 backends + 1 orchestrator) is significant. No blocking issues.

---

## Findings

### 1. Boundaries & Coupling

#### P3-1: SearchBackend protocol boundary is clean and stable

**Status**: Excellent
**Files**: `backend.py:102-125`

The `SearchBackend` protocol defines a minimal, stable contract:
- `build(units, texts, rebuild)` — takes raw text, handles embedding internally
- `search(query, k)` — returns `SearchResult` list
- `load()` / `save()` — persistence lifecycle
- `info()` — typed metadata query

**Why this works:**
- Each backend owns its embedding strategy (Ollama vs PyLate), preventing shared global embedder state
- No leaky abstractions: backends don't expose FAISS/PLAID internals
- `build()` taking raw text (not pre-computed vectors) prevents premature coupling to a single embedding approach

**Evidence of good boundary discipline:**
```python
# backend.py:110-116
def build(self, units: list[CodeUnit], texts: list[str], *, rebuild: bool = False) -> BackendStats: ...
```
Backends receive `texts`, not embeddings. This allows ColBERT to use multi-vector encoding and FAISS to use single-vector, without the caller knowing or caring.

---

#### P2-2: Shared types (CodeUnit, SearchResult) correctly lifted to backend.py

**Status**: Good (minor documentation gap)
**Files**: `backend.py:26-58`, `vector_store.py` (shim)

`CodeUnit` and `SearchResult` are domain types shared across all backends. Moving them from `vector_store.py` to `backend.py` is architecturally correct — they belong at the abstraction layer, not tied to FAISS.

**Minor gap:**
The docstring for `CodeUnit` says "Minimal metadata for retrieval - full code is fetched on demand" but doesn't document the `file_hash` field's purpose (incremental update change detection). This is a documentation issue, not a design flaw.

**Recommendation:**
Add one line to `CodeUnit` docstring:
```python
# For incremental updates
file_hash: str = ""  # Hash of file content when indexed (for change detection)
```

---

#### P3-3: Factory pattern (`get_backend()`) handles dependency detection cleanly

**Status**: Excellent
**Files**: `backend.py:169-223`

The factory function correctly:
1. Respects existing index metadata (doesn't force a backend switch mid-project)
2. Falls back to availability checks (`_colbert_available()`, `_faiss_available()`)
3. Provides clear error messages with install instructions

**Why this avoids common factory mistakes:**
- No global registry to maintain
- No dynamic import side effects (imports happen inside conditionals)
- Auto-detection reads from index, not environment (stable across machines)

```python
# backend.py:186-202
if backend == "auto":
    existing = _read_index_backend(project_path)  # Stable: from meta.json
    if existing in ("faiss", "colbert"):
        backend = existing
    else:
        # Only then check availability
        if _colbert_available(): ...
```

---

#### P2-4: Daemon caching of backend instance is correct but underdocumented

**Status**: Good (documentation gap)
**Files**: `daemon.py:614-619`

The daemon caches the `SearchBackend` instance in `self._semantic_backend` to keep the ColBERT model resident (~900MB). This is **correct** — reloading the PyLate model on every query would be prohibitively slow.

**Gap:**
The cache invalidation logic (line 605: `self._semantic_backend = None`) is only triggered on re-index. There's no mention of what happens if the user switches backends via `tldrs semantic index --backend=colbert` after starting with FAISS.

**Scenario:**
1. Daemon starts, loads FAISS backend, caches in `_semantic_backend`
2. User runs `tldrs semantic index --backend=colbert` (rebuilds with ColBERT)
3. Daemon invalidates cache (line 605)
4. Next search re-loads backend, detects `colbert` from `meta.json`, works correctly

**Actual behavior**: Correct.
**Risk**: Low (the invalidation is there, just not commented).

**Recommendation:**
Add a comment at line 605:
```python
# Invalidate cached backend so next search reloads from updated meta.json
self._semantic_backend = None
```

---

#### P3-5: Shim modules (embeddings.py, vector_store.py) are exemplary backward-compat strategy

**Status**: Excellent
**Files**: `embeddings.py`, `vector_store.py`

Both files are now ~30-line shims that re-export the real implementations from `faiss_backend.py` and `backend.py`. This is the **right way** to preserve API stability during a refactor.

**Why this works:**
- Old import paths still work: `from tldr_swinton.modules.semantic.embeddings import get_embedder`
- No code duplication (just re-exports)
- Clear docstrings explain the indirection

**Evidence:**
```python
# embeddings.py:1-6
"""
Backward-compatibility shim.

Real implementation lives in faiss_backend.py. This module re-exports
the public API that external code (evals, AGENTS.md examples) relies on.
"""
```

**No action needed.** This is how to do it.

---

### 2. Pattern Analysis

#### P3-6: Backend consolidation eliminates 4-class hierarchy in favor of 2 standalone implementations

**Status**: Excellent (complexity reduction)
**Files**: `faiss_backend.py:241-586`, `colbert_backend.py:32-445`

**Before:** `Embedder` base class → `OllamaEmbedder`/`SentenceTransformerEmbedder` subclasses, `VectorStore` manages FAISS, separate `BM25Store`, coordination logic in `index.py`.

**After:** `FAISSBackend` and `ColBERTBackend` are self-contained. Each inlines its embedding logic, owns its index, and handles persistence.

**Why this is better:**
- No polymorphic calls across embedding backends (FAISS uses Ollama OR sentence-transformers, not a shared interface)
- Each backend's embedding strategy is tightly coupled to its index format (ColBERT needs `pool_factor`, FAISS needs L2 normalization)
- Easier to test: `FAISSBackend.build()` is a single entry point, not 3 collaborating objects

**Complexity metric:**
- Old: 4 classes, 6 public methods across 3 files → 18 integration points
- New: 2 classes, 5 methods each → 10 integration points (44% reduction)

---

#### P2-7: Incremental update logic is duplicated across backends (acceptable)

**Status**: Acceptable duplication (separation of concerns wins)
**Files**: `faiss_backend.py:314-354`, `colbert_backend.py:113-176`

Both backends implement similar incremental update logic:
1. Load existing units and hashes
2. Partition incoming units into new/changed/unchanged
3. Re-encode only new/changed texts
4. Merge with existing vectors

**Duplication:**
~40 lines of similar partitioning logic in each backend's `build()` method.

**Why not extract:**
- FAISS stores vectors in a numpy matrix, ColBERT stores per-document multi-vectors in PLAID
- FAISS can reconstruct old vectors (`_reconstruct_all_vectors()`), ColBERT can't (deletion triggers rebuild threshold)
- The partitioning logic is interleaved with backend-specific decisions (e.g., ColBERT's 20% deletion threshold at line 152)

**Trade-off analysis:**
- **Cost of duplication:** ~40 lines, low risk (unit-hash change detection is stable logic)
- **Cost of shared abstraction:** Would need a `VectorMerger` interface with `can_delete()`, `reconstruct()`, etc. → premature generalization
- **Verdict:** Current duplication is **acceptable**. The logic is simple enough that duplication is clearer than abstraction.

**Recommendation:** No refactor needed. If a third backend arrives and also has this logic, reconsider a shared `IncrementalBuilder` mixin.

---

#### P3-8: Build-lock pattern is correctly duplicated (file-descriptor semantics differ)

**Status**: Correct duplication
**Files**: `faiss_backend.py:565-586`, `colbert_backend.py:425-445`

Both backends use `fcntl.flock()` for build serialization. The lock logic is identical (~15 lines), but this is **not duplication to remove**.

**Why:**
- Each backend locks its own directory (`self._lock_path`)
- FAISS locks `.tldrs/index/.build.lock`
- ColBERT locks `.tldrs/index/plaid/.build.lock`
- File descriptors are backend-local state (can't share a single lock across two index dirs)

**Verdict:** This is **intentional duplication** for isolation. If backends shared a lock, a FAISS build would block a ColBERT build, which is wrong (different index dirs, different processes).

---

#### P2-9: BM25 integration is backend-aware (minor coupling)

**Status**: Acceptable coupling (pragmatic choice)
**Files**: `index.py:392-414`

The BM25 build logic knows about ColBERT's directory structure:
```python
# index.py:400-402
if bi.backend_name == "colbert":
    bm25_dir = bm25_dir.parent  # Store BM25 in parent, not plaid subdir
```

**Why this exists:**
ColBERT stores its PLAID index in `.tldrs/index/plaid/`, but BM25 should be in `.tldrs/index/` (shared across backends, not backend-specific).

**Coupling analysis:**
- `index.py` knows backend names ("faiss", "colbert")
- `index.py` knows ColBERT's directory layout (PLAID subdir)

**Alternative design:**
Add `bm25_dir()` method to `SearchBackend` protocol:
```python
def bm25_dir(self) -> Path: ...
```
Then `FAISSBackend.bm25_dir()` returns `self.index_dir`, `ColBERTBackend.bm25_dir()` returns `self.index_dir.parent`.

**Trade-off:**
- **Current cost:** 3 lines of if-logic in `index.py`
- **Abstraction cost:** Another protocol method, more indirection
- **Risk:** Low (only 2 backends, BM25 is optional)

**Recommendation:** Keep as-is. If BM25 grows more backend-specific logic (e.g., different tokenization per backend), then add the protocol method.

---

#### P3-10: Identifier fast-path has backend introspection (minor smell, acceptable)

**Status**: Acceptable (duck-typing fallback)
**Files**: `index.py:502-528`

The `_identifier_search()` helper checks for backend methods:
```python
if hasattr(search_backend, "get_units_by_name"):
    matches = search_backend.get_units_by_name(query)
elif hasattr(search_backend, "_units"):
    matches = [u for u in search_backend._units.values() if u.name == query]
```

**Why this exists:**
- `FAISSBackend` stores units as a list, exposes `get_units_by_name()`
- `ColBERTBackend` stores units as a dict (`_units: dict[str, CodeUnit]`), no helper method

**Coupling:**
- Couples to backend internals (`_units` is a private field)
- Uses `hasattr()` duck-typing instead of protocol method

**Why this is acceptable:**
1. The identifier fast-path is an **optimization**, not core functionality
2. If it fails (new backend without `_units`), it returns `[]` and falls back to semantic search
3. Adding a `get_units_by_name()` method to the protocol forces every backend to implement name-based lookup, which may not map cleanly to PLAID's retrieval API

**Recommendation:** Document this in the protocol docstring:
```python
class SearchBackend(Protocol):
    """Protocol for semantic search backends.

    Backends MAY implement get_units_by_name(name: str) for identifier fast-path,
    but it's optional. If missing, index.py will attempt duck-typed access to _units.
    """
```

---

### 3. Simplicity & YAGNI

#### P3-11: BackendInfo dataclass is minimal and non-speculative

**Status**: Excellent
**Files**: `backend.py:91-99`

```python
@dataclass
class BackendInfo:
    backend_name: str
    model: str
    dimension: int
    count: int
    index_path: str
    extra: dict = field(default_factory=dict)
```

**Why this is good:**
- All fields are used by `cli.py` for status output
- `extra` dict is a pragmatic escape hatch for backend-specific metadata (ColBERT uses it for `pool_factor`, `incremental_updates`)
- No `created_at`, `version`, `schema_version` fields that would be added "just in case"

**Evidence of restraint:**
The `extra` dict is only populated with data that's **already being tracked** (ColBERT's `pool_factor`, `incremental_updates`). It's not a "future metadata dumping ground."

---

#### P3-12: Meta.json atomic writes use minimal PID-based temp files

**Status**: Excellent (no over-engineering)
**Files**: `faiss_backend.py:559-563`, `colbert_backend.py:419-423`

Both backends use the same atomic write pattern:
```python
tmp = path.with_suffix(f".tmp.{os.getpid()}")
tmp.write_text(json.dumps(data, indent=2))
tmp.replace(path)
```

**Why this is simple:**
- Uses `os.getpid()` for uniqueness (no UUIDs, no timestamp-based names)
- No cleanup needed (`.replace()` atomically removes the temp file)
- No retry logic, no timeout handling (fails fast)

**What was avoided:**
- Lockfile-based coordination for writes (unnecessary; builds already hold `fcntl.flock()`)
- Versioned backups (`meta.json.bak.1`, `meta.json.bak.2`, etc.)
- Transactional write-ahead logs

**Verdict:** Correct simplicity. The build lock already serializes writes, so atomic write is sufficient.

---

#### P2-13: ColBERT incremental update counter has no automated rebuild trigger

**Status**: Acceptable (nudge, not enforcement)
**Files**: `colbert_backend.py:160-165`

```python
if self._incremental_updates >= 20 and not needs_full_rebuild:
    logger.warning(
        "Index has %d incremental updates since last rebuild. "
        "Consider --rebuild for best quality.",
        self._incremental_updates,
    )
```

**Why this exists:**
PLAID's centroids drift with many incremental adds. After 20 updates, rebuild improves quality.

**What it doesn't do:**
- Doesn't auto-rebuild (user must pass `--rebuild`)
- Doesn't track accuracy degradation (just counts updates)

**Speculation check:**
Is the `incremental_updates` counter premature?
**Answer:** No. It's based on PLAID documentation ("centroids become stale"). The threshold (20) is conservative.

**Alternative considered (rejected):**
Auto-rebuild after N updates → **Rejected** because rebuilds are slow (~15s for LateOn-Code-edge model load). User should decide when to pay that cost.

**Verdict:** Current design (warn, don't auto-rebuild) is correct. No YAGNI violation.

---

#### P3-14: No premature unification of FAISS and ColBERT build paths

**Status**: Excellent restraint
**Files**: `faiss_backend.py:292-403`, `colbert_backend.py:85-205`

The two backends' `build()` methods have different strategies:
- **FAISS:** Embeds batch → vstack into matrix → `faiss.add(matrix)`
- **ColBERT:** Embeds batch → decides full-rebuild vs incremental → temp-dir atomic swap or in-place add

**Why no shared `_build_strategy()` abstraction:**
- FAISS incremental is vector-level (add rows to matrix)
- ColBERT incremental is document-level (PLAID's `add_documents()`)
- FAISS rebuild is cheap (re-add all vectors to new IndexFlatIP)
- ColBERT rebuild requires temp-dir atomic swap (PLAID files can't be mutated in-place)

**Verdict:** Forcing a shared build flow would require conditional branches at every step. Current separation is **correct**.

---

## Recommendations Summary

### Must-Fix (P1)
None.

### Should-Fix (P2)
1. **P2-2:** Add docstring for `CodeUnit.file_hash` field (1 line)
2. **P2-4:** Comment daemon cache invalidation logic (1 line)
3. **P2-9:** If BM25 integration grows more backend-specific logic, add `bm25_dir()` to protocol (defer until needed)

### Nice-to-Have (P3)
1. **P3-10:** Document optional `get_units_by_name()` in protocol docstring
2. **P2-7:** Monitor for third backend; if it arrives, reconsider shared incremental builder (defer)

---

## Architectural Patterns Used (Correctly)

1. **Protocol-based polymorphism** (`SearchBackend`) instead of inheritance
   - Why: Backends have no shared implementation, only contract
2. **Factory function** (`get_backend()`) with dependency detection
   - Why: Backends have mutually exclusive dependencies (faiss vs pylate)
3. **Shim modules** for backward compatibility
   - Why: Preserves import paths during refactor
4. **Backend-local embedding** (no shared global Embedder)
   - Why: FAISS and ColBERT have different embedding needs (single-vector vs multi-vector)
5. **Atomic writes via temp + rename**
   - Why: Prevents corruption on crash during metadata write
6. **Build locks** (fcntl.flock) for process-level serialization
   - Why: Multiple processes might build the same index concurrently

---

## Complexity Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Modules | 7 | 6 | -14% |
| Public classes | 6 | 4 | -33% |
| Cross-module imports (semantic pkg) | 12 | 7 | -42% |
| Lines (semantic pkg) | ~1800 | ~1950 | +8% |

**Analysis:**
Line count increased slightly (+150 lines) because:
- ColBERT backend added (~450 lines, new feature)
- Shim modules added (~60 lines, backward compat)
- Removed embeddings/vector_store original implementations (-350 lines, moved to faiss_backend)

Net: **Complexity went down** (fewer classes, clearer boundaries) despite more lines.

---

## Boundary Violations: None Detected

All cross-module dependencies are intentional and documented:
- `index.py` → `backend.py` (uses factory and types)
- `faiss_backend.py` → `backend.py` (implements protocol)
- `colbert_backend.py` → `backend.py` (implements protocol)
- `daemon.py` → `backend.py` (caches backend instance)
- `cli.py` → `index.py` (user-facing commands)
- `embeddings.py` → `faiss_backend.py` (shim re-exports)
- `vector_store.py` → `backend.py`, `faiss_backend.py` (shim re-exports)

No circular imports, no leaky abstractions, no hidden coupling.

---

## Conclusion

This refactor demonstrates strong architecture discipline. The backend abstraction is **necessary** (two implementations with different retrieval strategies), **minimal** (5 methods, no speculative extension points), and **correct** (embedding is backend-local, not shared).

The minor duplication (incremental update partitioning, build locks) is **intentional** — the backends have different constraints (FAISS can reconstruct vectors, ColBERT can't delete from PLAID) that make shared logic more complex than duplicated logic.

**Final verdict:** Ship it. No blocking issues, only documentation gaps (P2 items) and future monitoring suggestions (P3 items).

**Maintainability outlook:** Adding a third backend (e.g., Milvus, Qdrant) would be straightforward:
1. Implement `SearchBackend` protocol (5 methods)
2. Add backend name to factory's `_read_index_backend()` and `get_backend()` (2 lines each)
3. Add CLI choice to `--backend` argument (1 line)

No existing code would need to change. This is the hallmark of a good abstraction.
