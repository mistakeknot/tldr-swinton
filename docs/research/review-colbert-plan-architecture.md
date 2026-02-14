# Architecture Review: ColBERT Search Backend Plan

**Date:** 2026-02-14
**Reviewer:** Flux-drive Architecture & Design Reviewer
**Target:** `/root/projects/tldr-swinton/docs/plans/2026-02-14-colbert-search-backend.md`

## Executive Summary

This plan refactors `modules/semantic/` from hardcoded FAISS to a dual-backend architecture with a `SearchBackend` protocol. The abstraction is right-sized for the problem, the module boundaries are clear, and the backward compatibility strategy is sound. **APPROVE with two mandatory fixes and three structural recommendations.**

## Boundaries & Coupling

### 1. Backend Abstraction Boundary (Strong)

**Protocol design:**
```python
class SearchBackend(Protocol):
    def build(self, units: list[CodeUnit], texts: list[str], *, rebuild: bool = False) -> BackendStats
    def search(self, query: str, k: int = 10) -> list[SearchResult]
    def load() -> bool
    def save() -> None
    def info() -> dict
```

**Strengths:**
- **Encapsulation of fundamental difference**: `build()` taking `texts` (not pre-computed vectors) correctly encapsulates the FAISS vs ColBERT embedding divergence. FAISS needs single vectors, ColBERT needs multi-vector token embeddings. This is the right layer to hide that decision.
- **Minimal surface**: Five methods. No leakage of FAISS/PLAID internals into the protocol.
- **Reusable types**: `CodeUnit`, `SearchResult`, `BackendStats` are shared across backends. Good separation between domain model and backend implementation.

**Weakness:**
- **`info()` signature too loose**: Returning `dict` without a typed structure creates implicit coupling. Each backend will invent its own keys, and callers won't know what to expect. This is a boundary leak.

**FIX REQUIRED:** Replace `info() -> dict` with a typed `BackendInfo` dataclass:
```python
@dataclass
class BackendInfo:
    backend_name: str
    model: str
    dimension: int  # For single-vector: vector dim; for ColBERT: token dim
    count: int
    index_path: str
    extra: dict = field(default_factory=dict)  # For backend-specific metadata
```

This preserves extensibility via `extra` while establishing a stable contract for common fields.

### 2. Orchestration → Backend Coupling (Acceptable)

**Current flow:**
```python
# index.py:build_index()
units = _extract_code_units(...)
texts = [_build_embed_text(u) for u in units]
backend = get_backend(project_path, backend="auto")
stats = backend.build(units, texts, rebuild=rebuild)
backend.save()
```

**Analysis:**
- `index.py` owns text preparation (`_build_embed_text()`) — correct. This is shared logic across all backends (metadata formatting, path shortening, docstring truncation).
- `index.py` owns unit extraction (`_extract_code_units()`) — correct. This is the bridge to the core extraction API.
- `index.py` owns BM25 fast-path logic — correct. This is a cross-cutting concern (identifier exact-match) that should not live in any single backend.
- Backends own embedding, storage, retrieval — correct encapsulation.

**No leaks detected.** The boundary is stable.

### 3. FAISS Backend → Old Module Coupling (Transitional Debt)

**Plan states:**
> **Keep `embeddings.py` and `vector_store.py` as-is** for backward compatibility. `FAISSBackend` imports from them.

**Analysis:**
This is **transitional debt masquerading as backward compatibility**. The plan keeps old files because "FAISSBackend refactors existing code from embeddings.py + vector_store.py" — but the old files are NOT part of the public API. They are internal modules. The real public API is:
- `build_index()`
- `search_index()`
- CLI commands (`tldrs index`, `tldrs find`)

**What "backward compatibility" actually requires:**
1. Old indexes (`.tldrs/index/{vectors.faiss, units.json, meta.json}`) must load correctly.
2. CLI commands must work identically (no breaking changes to flags or output).
3. MCP tools must work identically.

**What it does NOT require:**
- Keeping `embeddings.py` and `vector_store.py` as separate, importable modules.

**PROBLEM:** The plan creates **three ways to do the same thing**:
1. `FAISSBackend` (new)
2. `embeddings.py` functions (old, delegating to `FAISSBackend`)
3. `vector_store.VectorStore` (old, used by `FAISSBackend` internally)

This violates the "one obvious way" principle and creates maintenance burden. If someone imports `from tldr_swinton.modules.semantic.embeddings import embed_text`, do they get the old code or the new code? The plan doesn't clarify.

**FIX REQUIRED:** Consolidate instead of delegate.

**Recommended approach:**
1. **Move `CodeUnit`, `SearchResult`, `make_unit_id`, `get_file_hash` to `backend.py`** (these are shared types, not FAISS-specific).
2. **Inline `VectorStore` logic into `FAISSBackend`** (it's a thin FAISS wrapper — no reason for the extra indirection).
3. **Inline `OllamaEmbedder` / `SentenceTransformerEmbedder` into `FAISSBackend`** (these are FAISS's embedding strategy, not shared).
4. **Delete `embeddings.py` and `vector_store.py` entirely.**
5. **Update `__init__.py` exports** to re-export the shared types from `backend.py`:
   ```python
   from .backend import SearchBackend, get_backend, BackendStats, BackendInfo, CodeUnit, SearchResult, make_unit_id, get_file_hash
   ```

**Result:** One import path, one source of truth. Existing code that imports from `modules.semantic` gets the new implementation transparently.

**Backward compatibility for indexes:** `FAISSBackend.load()` checks for existing `vectors.faiss` / `units.json` / `meta.json` files and loads them. No migration script needed.

### 4. Daemon Coupling (Acceptable with Caveat)

**Plan:**
> Cache the backend instance on `self._semantic_backend`

**Analysis:**
The daemon currently has no backend caching — it calls `build_index()` / `search_index()` directly, which instantiate fresh stores every time. The plan adds:
```python
self._semantic_backend = get_backend(str(self.project))
self._semantic_backend.load()
```

**Strengths:**
- Model residency for ColBERT (17s cold start → 6ms warm). Necessary.
- Consistent with daemon's role (in-memory indexes).

**Weakness:**
- **Silent backend selection at daemon start.** If the user has both backends installed and the daemon picks ColBERT, but the index was built with FAISS, the `load()` call will fail or return stale data.

**FIX REQUIRED:** The backend selection must read `meta.json` and use the backend that built the index:
```python
# In daemon._handle_semantic()
if self._semantic_backend is None:
    meta_path = self.project / ".tldrs/index/meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        backend_name = meta.get("backend", "faiss")  # Add "backend" field to meta.json
    else:
        backend_name = "auto"
    self._semantic_backend = get_backend(str(self.project), backend=backend_name)
    self._semantic_backend.load()
```

**Add to meta.json:**
```json
{
  "backend": "faiss" | "colbert",
  "version": "1.0",
  ...
}
```

This ensures the daemon uses the same backend that built the index.

## Pattern Analysis

### 1. Factory Pattern (Clean)

```python
def get_backend(project_path, backend="auto") -> SearchBackend:
    if backend == "auto":
        # try colbert → faiss → error
    elif backend == "colbert":
        # ColBERTBackend or error
    elif backend == "faiss":
        # FAISSBackend or error
```

**Analysis:**
- **Single responsibility**: The factory owns backend selection logic.
- **Fail-fast**: Raises `RuntimeError` if deps not installed. No silent fallbacks that hide misconfiguration.
- **Auto-detection is clear**: Try ColBERT first (if `pylate` importable), then FAISS (if `faiss` importable). Explicit precedence order.

**Recommendation:** Add `backend` field to `meta.json` so auto-detection can verify the index matches the available backend. If mismatch (e.g., index is ColBERT but `pylate` not installed), raise early with a clear error message.

### 2. Duplication in `_build_embed_text()` (Intentional)

**Plan:**
> `_build_embed_text()` stays (shared text preparation)

**Analysis:**
Both backends use the same text preparation (metadata labels, docstring truncation, path shortening). This is **intentional duplication at the data layer** — not code duplication. The function is called once per backend, producing the same text. This is correct.

**No issue.**

### 3. BM25 Store Independence (Correct)

**Plan:**
> BM25 for identifier fast-path only

**Analysis:**
BM25 is used only in the lexical fast-path (exact identifier match). ColBERT's per-token matching subsumes BM25 for natural language queries. The plan keeps BM25 for the fast-path and removes hybrid RRF fusion for ColBERT search.

**Strengths:**
- **Clear separation of concerns**: BM25 is an optimization for a specific case (identifier queries), not a core retrieval strategy.
- **No coupling**: BM25 is built and queried independently. It doesn't know about backends.

**Question:** Does the plan remove BM25 from `search_index()` when using ColBERT? The plan text says "ColBERT's per-token matching subsumes BM25" but Step 4 still shows `_build_bm25()` being called in `build_index()`.

**Clarification needed:** Should `ColBERTBackend.search()` use RRF fusion with BM25, or is it pure ColBERT? If pure, then `_build_bm25()` should be conditional:
```python
if isinstance(search_backend, FAISSBackend):
    _build_bm25(...)
```

If BM25 is used only for the identifier fast-path, then it should be built for BOTH backends (current code is correct).

**Recommendation:** Add a comment in `search_index()` clarifying the BM25 role:
```python
# BM25 is used ONLY for identifier fast-path (Class.method exact match).
# It is NOT used in semantic/ColBERT search fusion.
```

### 4. Anti-Pattern: Delegation Wrapper (In Old Code, Will Be Fixed)

**Current embeddings.py:**
```python
def embed_text(...):
    embedder = get_embedder(...)
    vector = embedder.embed(...)
    return EmbeddingResult(...)
```

This is **unnecessary indirection** if the new plan consolidates backends correctly. The old `embeddings.py` has two layers (`get_embedder()` + `OllamaEmbedder/SentenceTransformerEmbedder`) when one layer (`FAISSBackend` with internal embedding logic) is sufficient.

The plan keeps this indirection by having `FAISSBackend` import from `embeddings.py`. **This is the transitional debt flagged earlier.** The fix (inline into `FAISSBackend`) removes this anti-pattern.

## Simplicity & YAGNI

### 1. Abstraction Justified?

**Question:** Do we need the `SearchBackend` protocol, or can we just have FAISS and ColBERT as separate code paths with an if/else?

**Answer:** The protocol is justified because:
1. **Two fundamentally different backends exist today** (FAISS, ColBERT).
2. **The plan explicitly mentions future backends** (jina, Cohere).
3. **The protocol has 5 methods** (minimal surface).
4. **The backends share no code** (different embedding strategies, different indexes).

This is not premature abstraction — it's solving a present need (FAISS vs ColBERT) while enabling future extension.

**YAGNI check:** The protocol methods (`build`, `search`, `load`, `save`, `info`) are all used in the current plan. No speculative methods. **PASS.**

### 2. Metadata Complexity

**Plan:**
> `BackendStats` dataclass (total_units, new_units, unchanged_units, embed_model, backend_name)

**Analysis:**
- All fields are displayed in CLI output (`tldrs index` progress messages).
- `embed_model` / `backend_name` are recorded in `meta.json` for index info display.
- Incremental update logic (`new_units`, `unchanged_units`, `updated_units`) is **already implemented in the existing code** (see `index.py:build_index()` lines 461-487).

This is not new complexity — it's lifting existing logic into a typed structure. **Approved.**

### 3. Daemon Caching Complexity

**Plan:**
> First call loads model (~17s); subsequent calls reuse (~6ms)

**Question:** Is daemon model caching necessary, or can we lazy-load per query?

**Answer:** Necessary. ColBERT's 17s cold start is unacceptable for interactive CLI use. The daemon's entire purpose is to amortize slow operations (call graph parsing, AST indexing) across multiple queries. Model residency fits this pattern.

**YAGNI check:** The daemon already caches call graphs and AST indexes. Adding backend caching is consistent, not speculative. **PASS.**

### 4. Unnecessary Complexity: Keeping Old Files

**Already flagged above.** Keeping `embeddings.py` / `vector_store.py` as backward-compat wrappers is **accidental complexity**. The real requirement (load old indexes) is satisfied by `FAISSBackend.load()`. The extra files create maintenance burden without value.

**FIX: Delete old files, consolidate into backends.**

## File Structure Confusion

### Current Plan

```
modules/semantic/
├── backend.py           # NEW: SearchBackend protocol + factory
├── faiss_backend.py     # NEW: FAISSBackend
├── colbert_backend.py   # NEW: ColBERTBackend
├── index.py             # REFACTORED: backend-agnostic orchestration
├── embeddings.py        # KEPT: backward compat, delegates to faiss_backend
├── vector_store.py      # KEPT: CodeUnit/SearchResult, used by faiss_backend
├── bm25_store.py        # KEPT: identifier fast-path
```

**Problems:**
1. **Three import paths for the same functionality** (`FAISSBackend`, `embeddings.embed_text()`, `VectorStore`).
2. **Unclear ownership:** Does `vector_store.py` belong to FAISS or is it shared? (Answer: it's FAISS-specific, but the plan treats it as shared.)
3. **Dead code risk:** If `embeddings.py` delegates to `FAISSBackend`, but no code imports from `embeddings.py`, the delegation layer is unused cruft.

### Recommended Structure

```
modules/semantic/
├── backend.py           # SearchBackend protocol + factory + shared types (CodeUnit, SearchResult, etc.)
├── faiss_backend.py     # FAISSBackend (self-contained: embedding + FAISS logic inlined)
├── colbert_backend.py   # ColBERTBackend (self-contained: PyLate logic)
├── index.py             # Orchestration: extract units, call backend, build BM25
├── bm25_store.py        # BM25 lexical index (used by identifier fast-path in index.py)
├── __init__.py          # Re-exports from backend.py for public API
```

**Deleted:**
- `embeddings.py` (logic moved into `FAISSBackend`)
- `vector_store.py` (types moved to `backend.py`, VectorStore inlined into `FAISSBackend`)

**Benefits:**
1. **One source of truth per concept.** Want embeddings? Look in `faiss_backend.py`. Want ColBERT? Look in `colbert_backend.py`.
2. **Clear ownership.** Each backend file is self-contained.
3. **No delegation layers.** Direct imports from `backend.py`.

## Integration Risk: Daemon Backend Mismatch

**Scenario:**
1. User builds index with FAISS: `tldrs index --backend=faiss`
2. User installs `pylate`: `pip install pylate`
3. Daemon starts, calls `get_backend(backend="auto")`
4. Factory returns `ColBERTBackend` (because `pylate` is now importable)
5. Daemon tries to load FAISS index with ColBERTBackend → **FAILS**

**Root cause:** The factory's `"auto"` mode looks at **installed packages**, not at **what backend built the index**.

**Fix (already noted above):** Add `backend` field to `meta.json` and use it to override `"auto"`:
```python
def get_backend(project_path, backend="auto"):
    if backend == "auto":
        meta_path = Path(project_path) / ".tldrs/index/meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            backend = meta.get("backend", "auto")  # Use recorded backend
        # Now proceed with "colbert" or "faiss" or fall through to try-colbert-first
    ...
```

This ensures auto-detection respects the existing index.

## CLI Backward Compatibility

**Plan:**
> `--backend` option added to `tldrs semantic index`

**Analysis:**
- New flag is **optional** (defaults to `"auto"`).
- Existing command `tldrs index` works identically (auto-selects backend).
- Users can force a specific backend with `--backend=faiss` or `--backend=colbert`.

**No breaking changes.** Approved.

## MCP Tool Impact

**Plan:**
> `semantic` tool gains optional `backend` parameter for indexing

**Analysis:**
- MCP `semantic` tool currently has no `backend` parameter (not in the codebase).
- Adding it as optional is **backward compatible**.
- Search auto-detects from metadata (no parameter needed).

**No issues.**

## Testing Gap

**Plan states:**
> 1. **Unit tests:** Each backend class tested independently with small fixtures
> 2. **Integration test:** `build_index(backend="colbert")` → `search_index()` end-to-end
> 3. **Backward compat:** Existing `build_index()` with no `backend` param works as before (FAISS)
> 4. **Fallback:** If pylate not installed, `backend="auto"` falls back to FAISS
> 5. **Incremental:** Build, modify files, rebuild — verify only changed files re-encoded
> 6. **Deletion threshold:** Remove >20% of files, verify full rebuild triggers

**Missing test:**
- **Backend mismatch recovery:** User has FAISS index, installs `pylate`, runs `tldrs find`. Does it fail gracefully or corrupt the index?

**Add to test plan:**
> 7. **Backend mismatch:** Build index with `backend=faiss`, then call `search_index()` with `pylate` installed (triggers auto=colbert). Verify clean error or fallback to FAISS.

## Rollout Risk: Index Migration UX

**Plan:**
> 1. Ship as optional extra (`semantic-colbert`), FAISS remains default
> 2. Document in AGENTS.md: `pip install 'tldr-swinton[semantic-colbert]'`
> 3. After validation: make ColBERT preferred when available (auto-detection)

**Question:** What happens to users who upgrade to the ColBERT-enabled version without rebuilding their index?

**Answer (from plan):** Auto-detection reads `meta.json` and uses the backend that built the index. No forced migration.

**Remaining UX issue:** How does a user **switch** from FAISS to ColBERT?

**Current plan:** Run `tldrs index --backend=colbert --rebuild`

**Better UX:** Detect backend mismatch and prompt:
```
$ tldrs index
✓ Found existing index (backend: faiss)
  Note: ColBERT backend is available (better retrieval quality).
  To switch: tldrs index --backend=colbert --rebuild
```

This avoids silent rebuilds and gives users agency.

## Risks & Mitigations (From Plan)

| Risk | Mitigation | Review Comment |
|------|-----------|----------------|
| PyTorch ~1.7GB install | Optional extra only, FAISS stays lightweight default | Approved. Good separation. |
| Cold start ~17s on first query | Pre-warm on daemon start; lazy load in non-daemon CLI | Daemon pre-warm not in plan yet. Add to Step 5. |
| PLAID no delete | Rebuild threshold at 20% deletions | Acceptable. Document stale entry risk. |
| pylate-rs broken for this model | Use PyTorch PyLate; monitor pylate-rs for projection head fix | Acknowledged. No action needed. |
| Pool factor quality loss | Default pool_factor=2 (tested); make configurable | Approved. Configuration not in plan — add env var? |

**Additional risk not in plan:**
- **Daemon backend mismatch** (covered above, fix required).

## Recommendations Summary

### MANDATORY FIXES

1. **Add `BackendInfo` typed return for `info()` method** (replaces loose `dict`).
2. **Consolidate `embeddings.py` / `vector_store.py` into backends** (delete old files, inline logic).
3. **Add `backend` field to `meta.json`** and use it in daemon backend selection.

### STRUCTURAL IMPROVEMENTS

4. **Move shared types to `backend.py`** (`CodeUnit`, `SearchResult`, `make_unit_id`, `get_file_hash`).
5. **Clarify BM25 role in comments** (identifier fast-path only, not hybrid search).
6. **Add backend mismatch test** to test plan.

### OPTIONAL ENHANCEMENTS

7. **Daemon pre-warm** (load ColBERT model on daemon start if index uses ColBERT).
8. **Pool factor configuration** (env var `TLDRS_COLBERT_POOL_FACTOR`).
9. **Index switch UX** (detect backend mismatch, prompt user to rebuild).

## Final Verdict

**APPROVE with mandatory fixes.**

The plan correctly identifies the abstraction boundary (backend protocol), keeps orchestration logic separate, and avoids premature generalization. The three mandatory fixes address real coupling issues (loose `info()` contract, transitional debt in old files, daemon backend mismatch risk).

After fixes, the architecture will be:
- **Clear ownership:** Each backend is self-contained.
- **Stable boundaries:** Protocol methods are typed, shared types are centralized.
- **Low coupling:** Orchestration (`index.py`) depends only on the protocol, not on backend internals.
- **No dead code:** Old delegation layers removed.

This is a **right-sized refactor** for adding a second backend without architectural bloat.
