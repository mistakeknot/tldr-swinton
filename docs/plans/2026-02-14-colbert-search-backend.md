# Plan: ColBERT Late-Interaction Search Backend

**Bead:** tldr-swinton-wp7
**Phase:** plan-reviewed (as of 2026-02-14T21:30:00Z)
**Brainstorm:** `docs/brainstorms/2026-02-14-colbert-search-backend-brainstorm.md`
**Date:** 2026-02-14

## Summary

Add a ColBERT late-interaction search backend to `modules/semantic/` using PyLate + LateOn-Code-edge (17M params). Refactor the module to use a `SearchBackend` protocol so FAISS and PLAID are interchangeable. ColBERT is auto-preferred when pylate is installed; FAISS+Ollama is the fallback.

## Architecture

### SearchBackend Protocol

```python
class SearchBackend(Protocol):
    """Protocol for semantic search backends."""

    def build(self, units: list[CodeUnit], texts: list[str], *, rebuild: bool = False) -> BackendStats: ...
    def search(self, query: str, k: int = 10) -> list[SearchResult]: ...
    def load(self) -> bool: ...
    def save(self) -> None: ...
    def info(self) -> dict: ...
```

Both `FAISSBackend` and `ColBERTBackend` implement this. The backend handles its own embedding — `build()` takes raw text, not pre-computed vectors. This encapsulates the fundamental difference: FAISS needs single vectors, ColBERT needs multi-vector token embeddings.

### File Changes

```
modules/semantic/
├── __init__.py          # Updated exports
├── backend.py           # NEW: SearchBackend protocol + factory
├── faiss_backend.py     # NEW: FAISSBackend (refactored from embeddings.py + vector_store.py)
├── colbert_backend.py   # NEW: ColBERTBackend (PyLate wrapper)
├── index.py             # REFACTORED: backend-agnostic orchestration
├── embeddings.py        # KEPT: backward compat, delegates to faiss_backend
├── vector_store.py      # KEPT: backward compat, CodeUnit/SearchResult/get_file_hash stay
├── bm25_store.py        # KEPT: used by identifier fast-path only
```

## Steps

### Step 1: Create SearchBackend protocol (`backend.py`)

**File:** `src/tldr_swinton/modules/semantic/backend.py`

Define:
- `SearchBackend` protocol with `build()`, `search()`, `load()`, `save()`, `info()` methods
- `BackendStats` dataclass (total_units, new_units, unchanged_units, embed_model, backend_name)
- `get_backend(project_path, backend="auto") -> SearchBackend` factory function
  - `"auto"`: try colbert first (if pylate importable), then faiss (if faiss importable), else error
  - `"colbert"`: ColBERTBackend or error
  - `"faiss"`: FAISSBackend or error
- Re-export `CodeUnit`, `SearchResult`, `get_file_hash`, `make_unit_id` from `vector_store.py`

**Tests:** Unit test for factory function with mocked imports.

### Step 2: Create FAISSBackend (`faiss_backend.py`)

**File:** `src/tldr_swinton/modules/semantic/faiss_backend.py`

Refactor existing code from `embeddings.py` + `vector_store.py` into `FAISSBackend` class:

```python
class FAISSBackend:
    """FAISS single-vector search backend."""

    def __init__(self, project_path: str):
        self.project = Path(project_path).resolve()
        self.index_dir = self.project / ".tldrs" / "index"
        self._store: VectorStore | None = None
        self._embedder = None

    def build(self, units, texts, *, rebuild=False) -> BackendStats: ...
    def search(self, query, k=10) -> list[SearchResult]: ...
    def load(self) -> bool: ...
    def save(self) -> None: ...
    def info(self) -> dict: ...
```

Key behavior:
- `build()` embeds texts via `get_embedder()` (existing Ollama/sentence-transformers logic), stores in FAISS
- `search()` embeds query, searches FAISS, optionally fuses with BM25 via RRF
- Incremental update logic (file hash comparison) moves here from `index.py`
- All existing FAISS behavior preserved exactly

**Keep `embeddings.py` and `vector_store.py` as-is** for backward compatibility. `FAISSBackend` imports from them.

**Tests:** Verify existing `tldrs semantic search` works identically through the new class.

### Step 3: Create ColBERTBackend (`colbert_backend.py`)

**File:** `src/tldr_swinton/modules/semantic/colbert_backend.py`

```python
class ColBERTBackend:
    """ColBERT late-interaction search backend via PyLate."""

    MODEL = "lightonai/LateOn-Code-edge"
    POOL_FACTOR = 2
    INDEX_SUBDIR = "plaid"
    REBUILD_THRESHOLD = 0.20  # rebuild when >20% units deleted

    def __init__(self, project_path: str):
        self.project = Path(project_path).resolve()
        self.index_dir = self.project / ".tldrs" / "index" / self.INDEX_SUBDIR
        self._model = None  # Lazy-loaded, kept resident
        self._index = None
        self._retriever = None
        self._units: dict[str, CodeUnit] = {}  # id -> unit
        self._unit_hashes: dict[str, str] = {}  # id -> file_hash

    def _ensure_model(self):
        """Lazy-load PyLate model (kept resident in process)."""
        if self._model is None:
            from pylate import models
            self._model = models.ColBERT(model_name_or_path=self.MODEL)

    def build(self, units, texts, *, rebuild=False) -> BackendStats: ...
    def search(self, query, k=10) -> list[SearchResult]: ...
    def load(self) -> bool: ...
    def save(self) -> None: ...
    def info(self) -> dict: ...
```

Key behavior:

**build():**
1. Load existing index if not rebuild (check `self.index_dir/meta.json`)
2. Compare units by file_hash — partition into new, changed, unchanged, deleted
3. If deletions > REBUILD_THRESHOLD * total → full rebuild
4. Encode new/changed texts: `model.encode(texts, is_query=False, batch_size=32, pool_factor=2)`
5. `index.add_documents(ids, embeddings)` for incremental, or fresh PLAID index for rebuild
6. Save unit metadata to `meta.json` (unit list + hashes + backend info)

**search():**
1. Ensure model loaded
2. Encode query: `model.encode([query], is_query=True)`
3. Retrieve: `retriever.retrieve(query_embeddings, k=k)`
4. Map PLAID doc IDs back to CodeUnit objects
5. Return list[SearchResult] (same type as FAISS)

**Persistence:**
- PLAID index persists automatically to `self.index_dir/`
- Unit metadata (CodeUnit list + file hashes) stored in `self.index_dir/meta.json`
- On `load()`, read meta.json and point PLAID at existing index dir

**Tests:**
- End-to-end: build index from test fixtures, search, verify results
- Incremental: add files, verify only new files re-encoded
- Deletion threshold: remove files, verify rebuild triggers at 20%

### Step 4: Refactor `index.py` to use backend abstraction

**File:** `src/tldr_swinton/modules/semantic/index.py`

Replace `build_index()` internals:

```python
def build_index(
    project_path: str,
    language: str | None = None,
    backend: str = "auto",  # "auto" | "colbert" | "faiss"
    rebuild: bool = False,
    show_progress: bool = True,
    **kwargs,
) -> IndexStats:
    units = _extract_code_units(project_path, language, ...)
    texts = [_build_embed_text(u) for u in units]

    search_backend = get_backend(project_path, backend=backend)
    stats = search_backend.build(units, texts, rebuild=rebuild)
    search_backend.save()

    # BM25 for identifier fast-path (built regardless of backend)
    _build_bm25(search_backend.index_dir, units, texts)

    return IndexStats(...)
```

Replace `search_index()` internals:

```python
def search_index(
    project_path: str,
    query: str,
    k: int = 10,
    **kwargs,
) -> list[dict]:
    # Identifier fast-path (BM25, unchanged)
    if _IDENT_RE.match(query.strip()):
        ...  # existing exact match logic

    search_backend = get_backend(project_path, backend="auto")
    if not search_backend.load():
        raise FileNotFoundError("No index found. Run `tldrs index` first.")

    results = search_backend.search(query, k=remaining_k)
    return _format_results(exact_results, results)
```

Key changes:
- `_require_semantic_deps()` removed — each backend checks its own deps
- `_generate_summaries_ollama()` stays (called before backend.build())
- `_build_embed_text()` stays (shared text preparation)
- `_rrf_fuse()` only used by FAISSBackend internally
- `backend` parameter added to `build_index()` and `get_index_info()`
- `search_index()` auto-detects backend from stored metadata

### Step 5: Update daemon to cache ColBERT model

**File:** `src/tldr_swinton/modules/core/daemon.py`

In `_handle_semantic()`:
- Import `get_backend` instead of `build_index`/`search_index` directly
- Cache the backend instance on `self._semantic_backend`
- First call loads model (~17s); subsequent calls reuse (~6ms)

```python
def _handle_semantic(self, command: dict) -> dict:
    action = command.get("action", "search")
    try:
        if self._semantic_backend is None:
            from ..semantic.backend import get_backend
            self._semantic_backend = get_backend(str(self.project))
            self._semantic_backend.load()

        if action == "search":
            query = command.get("query")
            k = command.get("k", 10)
            results = self._semantic_backend.search(query, k=k)
            return {"status": "ok", "results": [r.to_dict() for r in results]}
        ...
```

### Step 6: Update pyproject.toml and __init__.py

**pyproject.toml** — add new extras:
```toml
semantic-colbert = [
    "pylate>=1.3.4",
    "rank-bm25>=0.2.2",
    "rich>=13.0",
]
```

Note: `pylate` pulls `torch`, `transformers`, `sentence-transformers`, `numpy` as transitive deps.

**`__init__.py`** — add new exports:
```python
from .backend import SearchBackend, get_backend, BackendStats
```

### Step 7: Update CLI and MCP tool

**cli.py:**
- Add `--backend` option to `tldrs semantic index`: `--backend auto|colbert|faiss`
- Pass through to `build_index(backend=...)`
- `tldrs semantic search` auto-detects from metadata

**mcp_server.py:**
- `semantic` tool gains optional `backend` parameter for indexing
- Search auto-detects (no change needed)

### Step 8: Add `.tldrsignore` patterns for PLAID index

Add to default `.tldrsignore`:
```
.tldrs/index/plaid/
```

Ensure PLAID index files don't get indexed by tldrs itself.

## Testing Strategy

1. **Unit tests:** Each backend class tested independently with small fixtures
2. **Integration test:** `build_index(backend="colbert")` → `search_index()` end-to-end
3. **Backward compat:** Existing `build_index()` with no `backend` param works as before (FAISS)
4. **Fallback:** If pylate not installed, `backend="auto"` falls back to FAISS
5. **Incremental:** Build, modify files, rebuild — verify only changed files re-encoded
6. **Deletion threshold:** Remove >20% of files, verify full rebuild triggers

## Rollout

1. Ship as optional extra (`semantic-colbert`), FAISS remains default
2. Document in AGENTS.md: `pip install 'tldr-swinton[semantic-colbert]'`
3. After validation: make ColBERT preferred when available (auto-detection)
4. Future: consider making ColBERT the default, FAISS the fallback

## Risks

| Risk | Mitigation |
|------|-----------|
| PyTorch ~1.7GB install | Optional extra only, FAISS stays lightweight default |
| Cold start ~17s on first query | Pre-warm on daemon start; lazy load in non-daemon CLI |
| PLAID no delete | Rebuild threshold at 20% deletions |
| pylate-rs broken for this model | Use PyTorch PyLate; monitor pylate-rs for projection head fix |
| Pool factor quality loss | Default pool_factor=2 (tested); make configurable |

## Review Amendments (Flux-Drive, 2026-02-14)

Incorporated from architecture, correctness, and UX reviews.

### Mandatory Changes (Applied to Steps Above)

1. **Typed `BackendInfo`** — `info()` returns `BackendInfo` dataclass, not loose `dict`. Fields: `backend_name`, `model`, `dimension`, `count`, `index_path`, `extra: dict`.

2. **Delete old files, consolidate into backends** — Per architecture review, `embeddings.py` and `vector_store.py` are transitional debt. `FAISSBackend` inlines their logic; shared types (`CodeUnit`, `SearchResult`, `make_unit_id`, `get_file_hash`) move to `backend.py`. Old files deleted.

3. **Add `backend` field to `meta.json`** — Factory's `"auto"` mode reads `meta.json` to detect which backend built the index. Prevents daemon backend mismatch (installing pylate doesn't silently switch from FAISS).

4. **Atomic index swap for rebuilds** — `build()` writes to temp dir, renames on success. Prevents concurrent search reading partially-written PLAID index.

5. **Atomic `meta.json` writes** — Write to `.tmp` file, then `os.replace()`. Prevents crash leaving inconsistent state.

6. **Build sentinel file** — `.build_in_progress` sentinel created before build, deleted after. On load, if sentinel exists, force full rebuild.

7. **Lock file for build serialization** — `fcntl.flock(LOCK_EX | LOCK_NB)` prevents concurrent builds (CLI + daemon auto-reindex).

8. **Rebuild threshold uses `>=`** — `deletions >= REBUILD_THRESHOLD * total` (not `>`).

9. **Cold-start feedback** — Log message during model load: `"Loading ColBERT model (first query only, ~17s)..."`. CLI shows spinner.

10. **Show backend in output** — Search results header shows `[Backend: colbert]` or `[Backend: faiss]`. Also shown in `tldrs semantic index` output.

11. **Migration detection nudge** — If FAISS index exists and pylate available, emit: `"ColBERT backend available. Rebuild for better quality: tldrs semantic index --backend=colbert"`

### Updated File Structure

```
modules/semantic/
├── __init__.py          # Updated exports (from backend.py)
├── backend.py           # SearchBackend protocol + factory + shared types
├── faiss_backend.py     # FAISSBackend (inlines embeddings.py + vector_store.py)
├── colbert_backend.py   # ColBERTBackend (PyLate wrapper)
├── index.py             # Backend-agnostic orchestration
├── bm25_store.py        # BM25 lexical index (identifier fast-path)
```

**Deleted:** `embeddings.py`, `vector_store.py` (logic consolidated into backends + backend.py)

### Deferred (Post-MVP)

- Per-unit content hashing (currently per-file)
- PLAID doc ID order assertion
- Centroid drift detection/measurement
- `tldrs semantic compare` A/B command
- ONNX/quantized model option
