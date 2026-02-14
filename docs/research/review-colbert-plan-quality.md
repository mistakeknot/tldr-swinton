# Review: ColBERT Search Backend Implementation Plan

**Date:** 2026-02-14
**Reviewer:** Flux-drive Quality & Style Reviewer
**Plan:** `/root/projects/tldr-swinton/docs/plans/2026-02-14-colbert-search-backend.md`

## Summary

The plan is **well-structured and implementation-ready** with strong architecture, good naming discipline, and comprehensive error handling. A few refinements would strengthen it: adopting ABC instead of Protocol for runtime validation, aligning "Backend" terminology with the codebase's existing "Engine" convention, adding granular error handling for partial index corruption scenarios, and expanding the test strategy to cover backend selection edge cases.

**Recommended before implementation:** Clarify ABC vs Protocol choice, decide on Backend vs Engine naming, and add corruption recovery tests.

---

## Universal Quality Review

### Naming Consistency

**Issue: Backend vs Engine Terminology**

The plan introduces `SearchBackend` as the abstraction, but the codebase already has a well-established "engine" convention in `modules/core/engines/` (difflens, symbolkite, cfg, dfg, pdg, delta, astgrep). Each engine exports a `get_*_context()` function.

**Current plan:**
- `SearchBackend` protocol
- `FAISSBackend` class
- `ColBERTBackend` class
- Factory: `get_backend()`

**Codebase pattern:**
- Engines are in `modules/core/engines/`
- Each engine module exports a function (`get_diff_context`, `get_cfg_context`, etc.)
- No classes currently use the "Engine" suffix — the module itself is the engine

**Options:**

1. **Keep "Backend" (plan as-is):** Justification: semantic search is a different layer than the 5-layer analysis engines. "Backend" signals infrastructure (FAISS, PLAID) vs analysis strategy (CFG, DFG). This is defensible — semantic search is orthogonal to the ContextPack pipeline.

2. **Rename to "Engine":** `SearchEngine`, `FAISSEngine`, `ColBERTEngine`, `get_search_engine()`. Aligns with codebase vocabulary but may blur the distinction between infrastructure (vector store) and analysis strategy (control flow, data flow).

3. **Rename to "Store":** The classes wrap vector stores (FAISS index, PLAID index). `SearchStore`, `FAISSStore`, `ColBERTStore`. But "store" already appears in `vector_store.py` (the VectorStore class wrapping FAISS).

**Recommendation:** Keep "Backend" for clarity, but document the distinction in code comments. The semantic module is infrastructure-focused (embedding + retrieval), not a ContextPack analysis engine. The naming is consistent internally (`FAISSBackend`, `ColBERTBackend`, `get_backend()`), which matters more than matching a distant module's convention.

**Minor naming issue:** `BackendStats` should mirror `IndexStats` structure. The plan defines `BackendStats(total_units, new_units, unchanged_units, embed_model, backend_name)` but `IndexStats` in `index.py` has `total_files, total_units, new_units, updated_units, unchanged_units, embed_model, embed_backend`. Consider:
- Renaming `backend_name` → `backend_type` (matches "embed_backend" pattern)
- Adding `deleted_units` to BackendStats for rebuild threshold logic visibility
- Clarifying that "unchanged_units" means "matched by file hash, skipped re-embedding"

### File Organization

**Good:** The plan keeps old files (`embeddings.py`, `vector_store.py`) for backward compatibility while refactoring logic into new backend files. This avoids breaking existing imports.

**Risk:** Two representations of the same concept (embedding + vector store) living side-by-side creates ambiguity. The plan says "FAISSBackend imports from them" but doesn't specify a deprecation timeline.

**Missing:** Clear module deprecation path. Add to the plan:
- Docstring warnings in `embeddings.py` and `vector_store.py`: "Deprecated. Use `backend.get_backend()` for new code."
- Timeline for removal (e.g., "Remove in v1.0 after 6-month deprecation window")
- Update AGENTS.md to document the new API as preferred

**File structure clarity:** The plan shows:
```
modules/semantic/
├── backend.py           # NEW: SearchBackend protocol + factory
├── faiss_backend.py     # NEW: FAISSBackend
├── colbert_backend.py   # NEW: ColBERTBackend
├── index.py             # REFACTORED
├── embeddings.py        # KEPT: backward compat, delegates to faiss_backend
├── vector_store.py      # KEPT: CodeUnit/SearchResult/get_file_hash stay
├── bm25_store.py        # KEPT: identifier fast-path only
```

This is clean. `backend.py` should re-export `CodeUnit`, `SearchResult`, `get_file_hash`, `make_unit_id` so new code can import everything from one place: `from tldr_swinton.modules.semantic.backend import get_backend, CodeUnit, SearchResult`.

### Error Handling Patterns

**Strong:** The existing codebase uses lazy import guards with informative error messages:

```python
try:
    import numpy as np
except ImportError as exc:
    np = None
    _NUMPY_IMPORT_ERROR = exc

def _require_numpy():
    if np is None:
        raise RuntimeError(
            "NumPy is required. Install with: pip install 'tldr-swinton[semantic-ollama]'"
        ) from _NUMPY_IMPORT_ERROR
```

**Plan compliance:** Step 1 says the factory function will error if backends are unavailable, but doesn't specify error messages or exception chaining. The backend classes should follow the existing pattern.

**Recommended error handling refinements:**

1. **Factory function granularity:**
   ```python
   def get_backend(project_path, backend="auto") -> SearchBackend:
       """
       Raises:
           RuntimeError: If requested backend is unavailable (missing deps)
           ValueError: If backend parameter is invalid
       """
       if backend == "auto":
           # Try ColBERT first
           try:
               return ColBERTBackend(project_path)
           except ImportError:
               pass  # Fall through to FAISS
           try:
               return FAISSBackend(project_path)
           except ImportError as exc:
               raise RuntimeError(
                   "No search backend available. "
                   "Install with: pip install 'tldr-swinton[semantic-ollama]' "
                   "or 'tldr-swinton[semantic-colbert]'."
               ) from exc
       elif backend == "colbert":
           try:
               return ColBERTBackend(project_path)
           except ImportError as exc:
               raise RuntimeError(
                   "ColBERT backend requires PyLate. "
                   "Install with: pip install 'tldr-swinton[semantic-colbert]'."
               ) from exc
       elif backend == "faiss":
           # ... similar
       else:
           raise ValueError(f"Unknown backend: {backend!r}. Choose 'auto', 'colbert', or 'faiss'.")
   ```

2. **Backend.__init__() should NOT import at construction time.** The existing `OllamaEmbedder` checks availability lazily via `is_available()`. ColBERTBackend's `_ensure_model()` is good. FAISSBackend should similarly defer FAISS import to first `build()` or `load()` call. This lets the factory function try multiple backends without triggering ImportError at construction.

3. **Partial index corruption:** What if `meta.json` exists but is corrupted? Or PLAID index dir exists but is incomplete? The plan doesn't specify. Recommendation:
   - `load()` should catch JSON decode errors and return `False` (same as "index doesn't exist")
   - Log a warning: `logger.warning("Corrupted index metadata at %s, rebuild required", meta_path)`
   - Add `--force-rebuild` flag to CLI as explicit override

4. **File hash mismatch on incremental update:** If a CodeUnit's file_hash doesn't match current file content, the unit is "changed" and re-embedded. But what if the file was deleted? The plan's `build()` pseudo-code doesn't show this. Recommendation:
   - Partition units into: new, changed, unchanged, **deleted**
   - Track `stats.deleted_units` for rebuild threshold
   - Filter deleted units from final index (don't embed ghosts)

### API Design Consistency

**Protocol methods:** The plan defines:
```python
class SearchBackend(Protocol):
    def build(self, units: list[CodeUnit], texts: list[str], *, rebuild: bool = False) -> BackendStats: ...
    def search(self, query: str, k: int = 10) -> list[SearchResult]: ...
    def load(self) -> bool: ...
    def save(self) -> None: ...
    def info(self) -> dict: ...
```

**Issue 1: `build()` takes both units and texts.** This duplicates data — the text could be derived from units via `_build_embed_text(u)`. But the plan explicitly says "backend handles its own embedding — build() takes raw text, not pre-computed vectors" to encapsulate the FAISS vs ColBERT difference.

**Tension:** If `build()` takes raw texts, why also take `units`? The backend needs units for metadata (file, line, name) to construct SearchResults later. But if `build()` is backend-agnostic, the orchestrator (`index.py`) should pass in parallel lists (units, texts) where `texts[i]` is the embeddable representation of `units[i]`.

**Current `index.py` pattern (lines 170-175 in plan):**
```python
units = _extract_code_units(project_path, language, ...)
texts = [_build_embed_text(u) for u in units]
search_backend = get_backend(project_path, backend=backend)
stats = search_backend.build(units, texts, rebuild=rebuild)
```

This is **correct and consistent**. The orchestrator prepares embeddable text via `_build_embed_text()` (which concatenates signature, docstring, summary). Each backend embeds the text its own way (FAISS → single vector, ColBERT → multi-vector). The backend stores `units` for retrieval metadata.

**No change needed** — the API design is sound.

**Issue 2: `info()` returns `dict`.** What keys? The plan doesn't specify. Look at existing `VectorStore.to_dict()`:
```python
@dataclass
class VectorStoreMetadata:
    version: str = "1.0"
    embed_model: str = ""
    embed_backend: str = ""
    dimension: int = 0
    count: int = 0
    project_root: str = ""
```

Recommendation: `info()` should return a similar structure. Define `BackendInfo` dataclass:
```python
@dataclass
class BackendInfo:
    backend_type: str  # "faiss" | "colbert"
    embed_model: str
    dimension: int | None  # None for ColBERT (variable per doc)
    total_units: int
    index_size_bytes: int
    last_updated: str  # ISO timestamp
```

This makes the return type explicit and enables type checking.

**Issue 3: `save()` has no return value.** What if save fails (disk full, permission error)? Recommendation:
- `save()` should raise `IOError` on failure (propagate OS errors)
- Document this in the Protocol docstring
- Callers should wrap in try/except if they need graceful degradation

### Complexity Budget

**Good:** The plan avoids over-abstraction. Two backend classes, one protocol, one factory function. No deep inheritance, no plugin system, no registry pattern. The complexity matches the problem scope (two backends, maybe 3-4 in the future).

**Potential creep:** The plan mentions "If we ever add jina, Cohere, or a future embedding model, we add a new backend class." But each new backend adds:
- A new class (50-150 lines)
- New optional dependencies (pyproject.toml extra)
- New error messages in the factory
- New test fixtures

**Risk mitigation:** Document a threshold for adding backends. Not every embedding model needs a dedicated backend — only architecturally distinct approaches (single-vector vs multi-vector, sparse vs dense). Fine-tuned variants of the same architecture (e.g., `nomic-embed-text` vs `nomic-embed-code`) should be config changes within the same backend, not new classes.

### Dependency Discipline

**New dependency:** `pylate>=1.3.4` pulls `torch`, `transformers`, `sentence-transformers`, `numpy` (~2GB install).

**Plan mitigation:** Optional extra `semantic-colbert`. FAISS remains the lightweight default. **This is correct.**

**Missing:** Pin torch to CPU-only wheel to avoid CUDA bloat. The plan mentions this in "Open Questions" but doesn't commit. Recommendation:
```toml
semantic-colbert = [
    "pylate>=1.3.4",
    "torch>=2.0,<3.0; platform_system != 'Darwin'",  # CPU-only on Linux
    "torch>=2.0,<3.0; platform_system == 'Darwin'",  # MPS on macOS
    "rank-bm25>=0.2.2",
    "rich>=13.0",
]
```

But this requires `--extra-index-url https://download.pytorch.org/whl/cpu` which pip/uv doesn't support in pyproject.toml. **Better:** Document in AGENTS.md:
```bash
# Install ColBERT backend (CPU-only torch)
pip install --extra-index-url https://download.pytorch.org/whl/cpu 'tldr-swinton[semantic-colbert]'
```

Or: use the default torch (includes CUDA), accept the bloat for users who install `[semantic-colbert]`. Most users won't install it — FAISS is default.

**Dependency on `rank-bm25`:** The plan keeps BM25 for identifier fast-path. But `rank-bm25` is only needed by FAISSBackend (ColBERT subsumes BM25 for natural language). Should it be in `semantic-colbert` extra? No — it's a shared dep, and it's tiny (pure Python, no heavy deps). Keep it in both `semantic-ollama` and `semantic-colbert`.

---

## Python-Specific Review

### Protocol vs ABC

**Plan choice:** `SearchBackend` defined as `typing.Protocol` (structural typing).

**Codebase context:** Zero existing uses of `Protocol` or `ABC` in the codebase (grep found none). This is the first abstraction of this kind in tldr-swinton.

**Protocol pros:**
- No explicit inheritance needed (`FAISSBackend` doesn't need `class FAISSBackend(SearchBackend)`)
- Duck typing — any object with the right methods satisfies the protocol
- Easier to retrofit to existing classes without touching their code

**Protocol cons:**
- No runtime validation — typos in method names won't fail until called
- No shared implementation logic (but this plan doesn't need any)
- Type checkers required to catch mistakes (mypy, pyright)

**ABC pros:**
- Runtime validation — `isinstance(obj, SearchBackend)` works
- Explicit contract — `class FAISSBackend(SearchBackend)` is self-documenting
- `@abstractmethod` forces implementations to define all methods

**ABC cons:**
- Explicit inheritance required
- Harder to retrofit (need to modify class definition)

**Recommendation for this codebase:** Use `ABC` instead of `Protocol`.

**Reasoning:**
1. **This codebase doesn't use type checking in CI.** There's no mypy/pyright in the workflow. Protocol benefits (static checking) won't be realized.
2. **Runtime validation is valuable here.** The factory function constructs backends dynamically based on string parameters (`"auto"`, `"faiss"`, `"colbert"`). `isinstance()` checks in tests and assertions would catch bugs.
3. **The classes are new code, not retrofits.** There's no existing `FAISSBackend` to avoid modifying — we're writing both the interface and implementations from scratch. Explicit inheritance is free.
4. **Precedent: codebase uses dataclasses, not TypedDict.** The existing code prefers runtime-validated structures (`@dataclass`) over static-only hints (`TypedDict`). ABC aligns with this.

**Revised API:**
```python
from abc import ABC, abstractmethod

class SearchBackend(ABC):
    """Abstract base class for semantic search backends."""

    @abstractmethod
    def build(self, units: list[CodeUnit], texts: list[str], *, rebuild: bool = False) -> BackendStats:
        """Build or update the search index."""
        ...

    @abstractmethod
    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        """Search the index."""
        ...

    @abstractmethod
    def load(self) -> bool:
        """Load index from disk. Returns False if not found."""
        ...

    @abstractmethod
    def save(self) -> None:
        """Persist index to disk."""
        ...

    @abstractmethod
    def info(self) -> BackendInfo:
        """Return backend metadata."""
        ...
```

### Type Hints

**Plan compliance:** The pseudo-code shows type hints on all public methods. Good.

**Missing:** Type hints on `_ensure_model()` and other private methods. The codebase (`embeddings.py`, `vector_store.py`) is **extensively typed** — even private functions have full annotations. The new backend classes should match this standard.

**Example from plan:**
```python
def _ensure_model(self):
    """Lazy-load PyLate model (kept resident in process)."""
    if self._model is None:
        from pylate import models
        self._model = models.ColBERT(model_name_or_path=self.MODEL)
```

**Should be:**
```python
def _ensure_model(self) -> None:
    """Lazy-load PyLate model (kept resident in process)."""
    if self._model is None:
        from pylate import models
        self._model = models.ColBERT(model_name_or_path=self.MODEL)
```

And the instance variable declarations in `__init__` should use type comments or annotated assignments:
```python
def __init__(self, project_path: str):
    self.project: Path = Path(project_path).resolve()
    self.index_dir: Path = self.project / ".tldrs" / "index" / self.INDEX_SUBDIR
    self._model: models.ColBERT | None = None
    self._index: PLAIDIndex | None = None  # or whatever PyLate's index class is
    self._retriever: PLAIDRetriever | None = None
    self._units: dict[str, CodeUnit] = {}
    self._unit_hashes: dict[str, str] = {}
```

### Exception Handling

**Plan coverage:** Step 3 says `build()` handles:
1. Load existing index
2. Compare file hashes
3. Partition units
4. Check deletion threshold
5. Encode texts
6. Update index

**Missing error scenarios:**

1. **PyLate model download fails:** `models.ColBERT(model_name_or_path=...)` downloads from HuggingFace if not cached. Network errors, auth failures, or model removal should be caught and wrapped:
   ```python
   def _ensure_model(self) -> None:
       if self._model is None:
           from pylate import models
           try:
               self._model = models.ColBERT(model_name_or_path=self.MODEL)
           except Exception as exc:
               raise RuntimeError(
                   f"Failed to load ColBERT model {self.MODEL}. "
                   "Check network connection and HuggingFace access."
               ) from exc
   ```

2. **PLAID index corruption:** `index.load()` might succeed (dir exists) but retrieval fails (corrupted centroid file). The plan doesn't address this. Recommendation:
   - Wrap `retriever.retrieve()` in try/except during `search()`
   - Catch PLAID-specific errors (whatever PyLate raises)
   - Log error and raise `RuntimeError("Index corrupted, rebuild required")`

3. **Embedding dimension mismatch:** If `meta.json` says dimension=768 but loaded model produces 48, the index is incompatible. This can happen if the user switches models without rebuilding. Recommendation:
   - Validate dimension in `load()`: `if loaded_meta['dimension'] != self.EXPECTED_DIM: return False`
   - For ColBERT, dimension is per-token (variable), so store model name instead: `if loaded_meta['model'] != self.MODEL: return False`

4. **File deletion during build:** `_extract_code_units()` scans files, then `build()` embeds them. If a file is deleted between scan and embed, `get_file_hash()` will fail. Existing code doesn't handle this. Recommendation:
   - Wrap `get_file_hash()` in `_extract_code_units()` with try/except
   - Skip deleted files with a debug log: `logger.debug("File deleted during scan: %s", path)`

### Testing Strategy

**Plan coverage (Step 8):**
1. Unit tests for each backend (small fixtures)
2. Integration test (build → search end-to-end)
3. Backward compat (existing `build_index()` with no `backend` param)
4. Fallback (pylate not installed → FAISS)
5. Incremental (modify files, verify only changed re-encoded)
6. Deletion threshold (remove >20%, verify rebuild triggers)

**Good scope.** Missing tests:

7. **Factory function with invalid backend string:** `get_backend(path, backend="invalid")` should raise `ValueError`. Test this.

8. **Factory function with missing deps for requested backend:** Request `"colbert"` but pylate not installed → should raise `RuntimeError` with install instructions, not fall back to FAISS. Test both explicit `"colbert"` and `"faiss"` requests.

9. **Index migration (FAISS → ColBERT):** User has existing `.tldrs/index/` (FAISS), runs `tldrs index --backend=colbert`. Should create `.tldrs/index/plaid/` without breaking old index. Test that both indexes can coexist.

10. **Corrupted `meta.json`:** Write invalid JSON to `meta.json`, call `load()`, verify returns `False` and doesn't crash.

11. **Partial PLAID index (missing files):** Create `meta.json` but delete PLAID centroid file. Call `load()`, verify returns `False`.

12. **Empty index (zero units):** Call `build(units=[], texts=[])`, verify doesn't crash, `save()` works, `load()` returns `True`, `search()` returns empty list.

13. **BM25 fast-path with ColBERT backend:** The plan says BM25 is for identifier fast-path only. Test that `search_index(query="verify_token")` uses BM25 (exact match) even when ColBERT is the backend. Verify `search_index(query="token verification logic")` uses ColBERT.

14. **Daemon model caching:** Test that `_handle_semantic()` caches the backend instance. First call loads model (~17s), second call reuses (fast). This is integration-level, may need mocking.

**Test organization:** Create `tests/test_semantic_backends.py` for backend unit tests, `tests/test_semantic_integration.py` for end-to-end. Keep existing `tests/test_semantic.py` (if it exists) for backward compat of old API.

---

## Architecture Review

### Protocol/ABC Choice (Revisited)

As discussed in the Python section, **ABC is recommended over Protocol** for this codebase. The plan should be updated in Step 1:

**Change:**
```python
# OLD (plan)
class SearchBackend(Protocol):
    ...

# NEW (recommended)
from abc import ABC, abstractmethod

class SearchBackend(ABC):
    @abstractmethod
    def build(...) -> BackendStats: ...
    # etc.
```

### Lazy Import Pattern

**Existing pattern (from `modules/core/engines/__init__.py`):**
```python
try:
    from .astgrep import get_structural_search, get_structural_context
    __all__.append("get_structural_search")
    __all__.append("get_structural_context")
except ImportError:
    pass
```

**Plan pattern (from factory function):**
```python
def get_backend(project_path, backend="auto") -> SearchBackend:
    if backend == "auto":
        try:
            return ColBERTBackend(project_path)
        except ImportError:
            pass
        try:
            return FAISSBackend(project_path)
        except ImportError as exc:
            raise RuntimeError(...) from exc
```

**Issue:** `ColBERTBackend(project_path)` shouldn't raise `ImportError` at construction time. The class exists even if pylate isn't installed. The import should fail inside `_ensure_model()` or at first `build()`/`search()` call.

**Recommended pattern:**
```python
# backend.py

def _colbert_available() -> bool:
    try:
        import pylate  # noqa: F401
        return True
    except ImportError:
        return False

def _faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
        return True
    except ImportError:
        return False

def get_backend(project_path: str, backend: str = "auto") -> SearchBackend:
    if backend == "auto":
        if _colbert_available():
            return ColBERTBackend(project_path)
        if _faiss_available():
            return FAISSBackend(project_path)
        raise RuntimeError(
            "No search backend available. "
            "Install with: pip install 'tldr-swinton[semantic-ollama]' "
            "or 'tldr-swinton[semantic-colbert]'."
        )
    elif backend == "colbert":
        if not _colbert_available():
            raise RuntimeError(
                "ColBERT backend requires PyLate. "
                "Install with: pip install 'tldr-swinton[semantic-colbert]'."
            )
        return ColBERTBackend(project_path)
    elif backend == "faiss":
        if not _faiss_available():
            raise RuntimeError(
                "FAISS backend requires faiss-cpu. "
                "Install with: pip install 'tldr-swinton[semantic-ollama]'."
            )
        return FAISSBackend(project_path)
    else:
        raise ValueError(f"Unknown backend: {backend!r}. Choose 'auto', 'colbert', or 'faiss'.")
```

This decouples import checking from class construction, making the factory function more testable (you can mock `_colbert_available()`).

### Daemon Caching Strategy

**Plan (Step 5):**
```python
def _handle_semantic(self, command: dict) -> dict:
    if self._semantic_backend is None:
        from ..semantic.backend import get_backend
        self._semantic_backend = get_backend(str(self.project))
        self._semantic_backend.load()
```

**Issue 1:** What if `load()` returns `False` (no index exists)? The daemon should handle this gracefully:
```python
def _handle_semantic(self, command: dict) -> dict:
    if self._semantic_backend is None:
        from ..semantic.backend import get_backend
        self._semantic_backend = get_backend(str(self.project))
        if not self._semantic_backend.load():
            return {"status": "error", "message": "No index found. Run 'tldrs index' first."}
```

**Issue 2:** What if the user rebuilds the index with a different backend while the daemon is running? The cached `_semantic_backend` is now stale. Recommendation:
- Add a `backend_type` field to the daemon's cached state
- On each request, check `backend.info()['backend_type']` against the on-disk `meta.json`
- If mismatch, reload: `self._semantic_backend = None; return self._handle_semantic(command)`

Or: simpler approach — make `tldrs index` shut down the daemon before rebuilding. Add a note in AGENTS.md: "Rebuilding the index with a different backend requires restarting the daemon."

**Issue 3:** The plan says "First call loads model (~17s); subsequent calls reuse (~6ms)". But Step 5 shows `_ensure_model()` called inside `search()`, not at `_handle_semantic()` entry. This means the first **search** is slow, but the daemon could pre-warm on startup. Recommendation:
- Add optional pre-warming: `if self._semantic_backend and hasattr(self._semantic_backend, '_ensure_model'): self._semantic_backend._ensure_model()`
- Or: accept the one-time 17s hit on first search (simpler, acceptable for daemon use case)

### Incremental Update Logic

**Plan (ColBERTBackend.build() pseudo-code, lines 130-136):**
1. Load existing index
2. Compare units by file_hash
3. Partition into new, changed, unchanged, deleted
4. If deletions > 20% → full rebuild
5. Encode new/changed texts
6. `index.add_documents()` for incremental

**Missing detail:** How is "deleted" detected? The `build()` method receives `units` (current scan) and can load `_unit_hashes` (previous scan) from `meta.json`. Deleted units are in previous but not current.

**Recommended algorithm:**
```python
def build(self, units: list[CodeUnit], texts: list[str], *, rebuild: bool = False) -> BackendStats:
    # Load existing state
    if not rebuild and self.load():
        old_ids = set(self._units.keys())
        new_ids = {u.id for u in units}
        deleted_ids = old_ids - new_ids

        if len(deleted_ids) > 0.20 * len(old_ids):
            logger.info("Deletion threshold exceeded (%d/%d units deleted), rebuilding index",
                        len(deleted_ids), len(old_ids))
            rebuild = True

    if rebuild:
        self._units = {}
        self._unit_hashes = {}
        self._index = None
        # ... full rebuild
    else:
        # ... incremental
        # Filter out deleted units from self._units
        for del_id in deleted_ids:
            del self._units[del_id]
            del self._unit_hashes[del_id]
```

**PLAID caveat:** The plan says "PLAID can't delete documents". If we filter deleted units from `self._units`, they're removed from the metadata but their embeddings remain in the PLAID index. This means:
- Search may return deleted units
- Filtering happens at result formatting time (check file exists)
- Storage bloat accumulates until rebuild

This is **acceptable** per the plan, but should be documented in the `ColBERTBackend` class docstring:
```python
class ColBERTBackend:
    """ColBERT late-interaction search backend via PyLate.

    PLAID indexes cannot delete documents. Deleted units are filtered from
    metadata but their embeddings remain in the index until a full rebuild.
    Rebuilds are triggered when deletions exceed 20% of total units.
    """
```

### BM25 Integration

**Plan (Step 4, lines 178-179):**
```python
# BM25 for identifier fast-path (built regardless of backend)
_build_bm25(search_backend.index_dir, units, texts)
```

**Issue:** `_build_bm25()` doesn't exist in the codebase. The plan says "BM25 for identifier fast-path only" but `bm25_store.py` is "KEPT: used by identifier fast-path only". This implies BM25 is already implemented.

**Check existing code:** `bm25_store.py` exists (plan confirms). The plan should clarify:
- Is `_build_bm25()` a new function or does `bm25_store.py` already have a build function?
- If new, define its signature: `_build_bm25(index_dir: Path, units: list[CodeUnit], texts: list[str]) -> None`
- If existing, document which function from `bm25_store.py` is used

**Identifier fast-path logic (Step 4, lines 192-194):**
```python
# Identifier fast-path (BM25, unchanged)
if _IDENT_RE.match(query.strip()):
    ...  # existing exact match logic
```

This suggests BM25 is only for exact identifier matches (regex-based). But the plan also says "BM25 for identifier fast-path" and MEMORY.md says "BM25 hybrid search → RRF fusion". These are contradictory.

**Clarification needed:**
1. **Exact match only:** If query matches `_IDENT_RE` (e.g., `verify_token`, `ClassName.method`), use BM25 for lexical exact matching. No semantic search, no fusion.
2. **Hybrid search:** For natural language queries, fuse BM25 + semantic via RRF.

The plan says "ColBERT's per-token matching subsumes BM25's lexical advantage for natural language queries." This implies **exact match only** (option 1). But the existing code (MEMORY.md commit 108e271) added RRF fusion for all queries.

**Recommendation:** Clarify in the plan:
- **FAISSBackend:** Uses BM25+RRF fusion for all non-identifier queries (existing behavior, keep it)
- **ColBERTBackend:** No BM25 fusion (ColBERT handles lexical internally). Only use BM25 for exact identifier fast-path.
- Update `search_index()` logic to make BM25 fusion backend-specific:
  ```python
  if _IDENT_RE.match(query.strip()):
      # Exact identifier match via BM25 (all backends)
      ...
  else:
      # Semantic search
      if isinstance(search_backend, FAISSBackend):
          results = search_backend.search(query, k=k)  # FAISS does RRF fusion internally
      elif isinstance(search_backend, ColBERTBackend):
          results = search_backend.search(query, k=k)  # ColBERT, no fusion
  ```

But this couples `search_index()` to backend types (bad). Better: make BM25 fusion a backend responsibility. FAISSBackend does it, ColBERTBackend doesn't. Move `_rrf_fuse()` into FAISSBackend.search().

---

## Missing Pieces

### 1. Index Migration UX

**Plan mention:** "Open Questions #3: Users with existing FAISS indexes need a clear path."

**Not in the plan:** Concrete migration steps.

**Recommendation:** Add to Step 7 (CLI updates):
```bash
# Detect existing index backend
tldrs semantic info
# Output: "Backend: faiss, Model: nomic-embed-text-v2-moe, Units: 1234"

# Migrate to ColBERT (rebuilds index)
tldrs semantic index --backend=colbert --rebuild

# Both indexes coexist (.tldrs/index/ for FAISS, .tldrs/index/plaid/ for ColBERT)
# Last-built index is used by default
```

**Implementation:** `get_backend(backend="auto")` should check which index exists (FAISS `faiss.index` file or ColBERT `plaid/meta.json`). If both exist, use the one with the newest `last_updated` timestamp. Add `last_updated` field to `BackendInfo`.

### 2. Daemon Pre-warming

**Plan mention:** "Open Questions #2: Should we pre-warm on daemon start?"

**Not in the plan:** Decision or implementation.

**Recommendation:** Add to Step 5 (daemon changes):
- Add `--no-prewarm` flag to daemon CLI (opt-out)
- Default: pre-warm ColBERT model on daemon start if `semantic-colbert` is installed
- Startup sequence: `get_backend() → load() → _ensure_model()` (if ColBERTBackend)
- Log startup time: "ColBERT model loaded in 16.9s"

### 3. Truncation/Limits for Large Queries

**Not mentioned:** What if a query returns 10,000 results? Or what if a single CodeUnit is 5000 lines (huge class)?

**Existing pattern:** `context`, `diff-context`, and `slice` commands have `--max-lines` and `--max-bytes` truncation (AGENTS.md line 197-200).

**Recommendation:** `search_index()` should similarly truncate large results. Add to `SearchBackend.search()` signature:
```python
def search(self, query: str, k: int = 10, max_result_size: int | None = None) -> list[SearchResult]:
    """
    Args:
        max_result_size: Optional per-result size limit in chars. Results exceeding
                        this are truncated with a marker.
    """
```

Or: keep it simple — `k` already limits result count. Truncation happens at formatting time (in CLI/MCP), not in the backend.

### 4. Observability/Logging

**Plan coverage:** Steps mention `logger.info()` and `logger.debug()` in pseudo-code. Good.

**Missing:** Log **what** at **which level**.

**Recommendation:** Add logging standards to the plan:
- `logger.debug()`: File-level incremental decisions ("File unchanged, skipping: foo.py")
- `logger.info()`: Build/search summary ("Indexed 1234 units in 5.2s", "Rebuild triggered: 250/1000 units deleted")
- `logger.warning()`: Recoverable issues ("Corrupted meta.json, rebuilding", "PyLate model download slow")
- `logger.error()`: Should-never-happen errors ("PLAID retrieval failed despite successful load()")

**Rich progress bars:** The plan shows `show_progress: bool` in `build_index()` signature (line 167). But the backend's `build()` method doesn't take this parameter. How does progress work?

**Recommendation:** Either:
1. Pass `show_progress` to `backend.build()` and let backends show their own progress bars
2. Keep progress in the orchestrator (`index.py`): `build_index()` shows a spinner while `backend.build()` runs

Option 2 is simpler (backends don't need Rich dependency). But ColBERT's encoding is the slow part — a progress bar over units would be valuable. Option 1 is better.

**Revised `SearchBackend.build()` signature:**
```python
@abstractmethod
def build(
    self,
    units: list[CodeUnit],
    texts: list[str],
    *,
    rebuild: bool = False,
    show_progress: bool = True,
) -> BackendStats:
```

---

## Risks & Mitigations

**Plan risks (lines 293-301):**

| Risk | Mitigation (Plan) | Quality Review |
|------|-------------------|----------------|
| PyTorch ~1.7GB install | Optional extra, FAISS default | ✅ Good. Consider CPU-only torch. |
| Cold start ~17s | Pre-warm on daemon start; lazy load in CLI | ⚠️ Decision needed (addressed above). |
| PLAID no delete | Rebuild threshold at 20% | ✅ Good. Document in class docstring. |
| pylate-rs broken | Use PyTorch PyLate; monitor for fix | ✅ Good. Add note to AGENTS.md. |
| Pool factor quality loss | Default pool_factor=2 (tested); make configurable | ⚠️ How configurable? Env var? CLI flag? |

**Additional risks not in plan:**

| Risk | Mitigation |
|------|-----------|
| ColBERT slower than FAISS on small queries | Document perf characteristics. For <100 units, FAISS may be faster. |
| User accidentally ships `.tldrs/index/plaid/` to Git (large files) | `.tldrsignore` pattern (plan Step 8). Also add to default `.gitignore` template. |
| Backend mismatch (built with FAISS, searched with ColBERT) | Store backend type in `meta.json`. Validate on `load()`. Factory auto-detects from metadata. |
| Concurrent writes (daemon + CLI both indexing) | File locking or detect daemon and send index command to daemon. Existing problem, not new. |

---

## Final Recommendations

### Before Implementation

1. **Decide: ABC vs Protocol.** Recommended: ABC for runtime validation.
2. **Decide: Backend vs Engine naming.** Recommended: Keep "Backend" but document distinction.
3. **Decide: Daemon pre-warming.** Recommended: Yes, opt-out via `--no-prewarm`.
4. **Decide: BM25 fusion scope.** Recommended: FAISS-only, document in plan.
5. **Decide: pool_factor configurability.** Recommended: Class constant for v1, env var (`TLDRS_COLBERT_POOL_FACTOR`) for tuning.

### Plan Refinements

1. **Step 1 (backend.py):**
   - Change `Protocol` → `ABC`
   - Define `BackendInfo` dataclass for `info()` return type
   - Add `_colbert_available()` and `_faiss_available()` helpers
   - Improve factory error messages (per "Error Handling" section above)

2. **Step 2 (faiss_backend.py):**
   - Move RRF fusion (`_rrf_fuse()`) from `index.py` into `FAISSBackend.search()`
   - Add type hints to all methods (including private)
   - Add deprecation warning to `embeddings.py` (docstring + AGENTS.md note)

3. **Step 3 (colbert_backend.py):**
   - Add class docstring explaining PLAID no-delete caveat
   - Wrap `models.ColBERT()` in try/except with helpful error
   - Add `show_progress` parameter to `build()`
   - Store `last_updated` timestamp in `meta.json`

4. **Step 4 (index.py):**
   - Remove `_require_semantic_deps()` (backends check their own deps)
   - Keep BM25 build for all backends (identifier fast-path)
   - Clarify BM25 fusion is FAISS-only (remove from orchestrator, move to backend)

5. **Step 5 (daemon.py):**
   - Handle `load()` returning `False`
   - Add optional pre-warming with `--no-prewarm` flag
   - Document daemon restart requirement for backend changes (AGENTS.md)

6. **Step 7 (CLI/MCP):**
   - Add `tldrs semantic info` to show current backend type
   - Document migration workflow in `--help` text
   - Add index coexistence note (FAISS + ColBERT can both exist)

7. **Step 8 (testing):**
   - Add tests for factory error cases (#7-#8 from "Testing Strategy" section)
   - Add index migration test (#9)
   - Add corrupted index tests (#10-#11)
   - Add BM25 fast-path test (#13)

8. **New Step 9 (documentation):**
   - Update AGENTS.md: new backend API, migration guide, performance notes
   - Add to MEMORY.md: "ColBERT via PyLate, PLAID no-delete, 20% rebuild threshold"
   - Update plugin quickstart if semantic search commands are affected

### Code Quality Checklist (Implementation Phase)

When implementing, verify:

- [ ] All public methods have type hints (args + return)
- [ ] All private methods have type hints
- [ ] All exceptions chained with `from exc` (preserves traceback)
- [ ] All `ImportError` have install instructions in the message
- [ ] All file I/O wrapped in try/except with informative errors
- [ ] All dataclasses use `@dataclass` decorator (not manual `__init__`)
- [ ] All dict returns replaced with dataclass instances (BackendInfo, BackendStats)
- [ ] All logger calls at appropriate level (debug/info/warning/error)
- [ ] All new files have module docstrings
- [ ] All backend classes have class docstrings explaining behavior
- [ ] No hardcoded paths (use `Path(project_path).resolve()`)
- [ ] No global state (all state in class instances)
- [ ] No subprocess without error handling
- [ ] Tests cover happy path + error cases + edge cases (empty index, corruption, missing deps)

---

## Conclusion

The plan is **well-designed and nearly implementation-ready**. The architecture is sound (backend abstraction), the naming is mostly consistent (minor "Backend" vs "Engine" ambiguity), and the error handling strategy exists (needs more detail). The main gaps are:

1. **ABC vs Protocol** — use ABC for runtime validation
2. **Backend vs Engine** — document the distinction, keep "Backend"
3. **Error handling granularity** — add corruption recovery, model load failures
4. **Test coverage** — add 6 missing test scenarios
5. **BM25 fusion scope** — clarify FAISS-only, update plan
6. **Daemon pre-warming** — commit to yes/no, add to plan
7. **Migration UX** — add concrete migration steps to Step 7

Addressing these refinements before implementation will reduce mid-implementation confusion and ensure the code matches the codebase's quality standards.

**Overall assessment:** 8/10. With the above refinements: 9.5/10.
