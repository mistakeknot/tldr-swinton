# Integration Tests for Semantic Search Backends

## Task
Write integration tests for the `tldr-swinton` semantic search backends (`FAISSBackend`, `ColBERTBackend`, factory `get_backend()`, and shared types).

## Files Analyzed

- `/root/projects/tldr-swinton/src/tldr_swinton/modules/semantic/backend.py` -- Protocol, factory, shared types (`CodeUnit`, `SearchResult`, `BackendInfo`, `BackendStats`, `get_backend()`, `_read_index_backend()`, `make_unit_id()`)
- `/root/projects/tldr-swinton/src/tldr_swinton/modules/semantic/faiss_backend.py` -- FAISS single-vector backend with Ollama/sentence-transformers embedders, incremental indexing, BM25 RRF fusion
- `/root/projects/tldr-swinton/src/tldr_swinton/modules/semantic/colbert_backend.py` -- ColBERT multi-vector backend via PyLate with PLAID indexing
- `/root/projects/tldr-swinton/tests/test_semantic_errors.py` -- Existing: load nonexistent, empty units, missing unit ID (3 tests)
- `/root/projects/tldr-swinton/tests/test_semantic_deps.py` -- Existing: `_require_numpy`/`_require_faiss` missing import paths (2 tests)

## Architecture Observations

1. **Backend Protocol**: `SearchBackend` is a `@runtime_checkable` Protocol with `build()`, `search()`, `load()`, `save()`, `info()` methods. Both backends implement this interface.

2. **Embedding is internal to build()**: `FAISSBackend.build()` calls `_get_embedder()` internally. To test without Ollama/sentence-transformers, we must monkeypatch `_get_embedder` at the module level.

3. **Incremental updates**: `FAISSBackend.build()` loads existing index from disk (via `self.load()`), compares `file_hash` fields, and only re-embeds changed units. Testing this requires `save()` between builds.

4. **ColBERT has no mock-friendly path**: The `ColBERTBackend` deeply integrates with PyLate (model loading, PLAID indexing). Integration testing build/search would require PyLate installed. The error paths (load with no index, sentinel) are testable without it.

5. **Sentinel pattern**: Both backends write a `.build_in_progress` sentinel file at build start, remove on success. `load()` detects this and returns False (cleaning up the sentinel).

6. **Thread safety**: Both backends use `threading.RLock()` for concurrent build/search safety. Not tested here (would need threading tests).

## Test Design Decisions

### Mock Strategy
- **`_FakeEmbedder`**: A deterministic embedder that generates L2-normalized numpy vectors from text hash seeds. This allows FAISS build/search to work end-to-end without Ollama or sentence-transformers.
- **`monkeypatch.setattr(fb_mod, "_get_embedder", ...)`**: Patches at the module level so both `build()` and `search()` use the fake embedder.
- **`@needs_faiss` skipif marker**: Tests requiring numpy/faiss skip gracefully on minimal installs.

### What's NOT Tested (and why)
- **ColBERT build/search**: Requires PyLate (~1.7GB dependency). Only error paths tested.
- **BM25 hybrid fusion**: `search()` tries BM25 fusion but gracefully falls back. The mock test exercises the pure-semantic path.
- **Concurrent build/search threading**: Would need `threading.Thread` orchestration. Out of scope for this test file.
- **Existing tests not duplicated**: `test_semantic_errors.py` already covers load-nonexistent, empty-units, missing-unit-id. `test_semantic_deps.py` covers `_require_numpy`/`_require_faiss` error paths.

## Tests Written

File: `/root/projects/tldr-swinton/tests/test_semantic_backends.py`

### 1. FAISSBackend Build/Search Cycle (3 tests)
- `test_build_and_search_returns_results` -- Build 3 units, search, verify all 3 returned as SearchResult with correct types
- `test_search_returns_correct_metadata` -- Build 1 unit, search, verify name/file/line/score metadata
- `test_search_empty_index_returns_empty` -- Search without building returns `[]`

### 2. FAISSBackend Incremental Update (1 test)
- `test_incremental_stats` -- Build 3 units, save, rebuild with 1 changed hash. Verify `new=0, updated=1, unchanged=2`.

### 3. ColBERT Load Error Paths (2 tests)
- `test_load_returns_false_no_index` -- Fresh tmp_path, no meta.json
- `test_load_returns_false_sentinel_exists` -- Sentinel file present (partial build)

### 4. Backend Selection via get_backend() (6 tests)
- `test_faiss_explicit` -- `backend="faiss"` returns FAISSBackend
- `test_colbert_unavailable_raises` -- `backend="colbert"` with `_colbert_available=False` raises RuntimeError
- `test_unknown_backend_raises` -- `backend="nonexistent"` raises ValueError
- `test_auto_reads_existing_meta` -- Writes meta.json with `"backend": "faiss"`, verifies auto picks FAISS even when colbert "available"
- `test_auto_no_backends_raises` -- Both backends unavailable raises RuntimeError
- `test_auto_prefers_colbert_when_available` -- No existing index + colbert available = picks colbert

### 5. Sentinel Cleanup (2 tests)
- `test_faiss_sentinel_cleaned_on_load` -- Create sentinel, call load(), verify False + sentinel removed
- `test_colbert_sentinel_cleaned_on_load` -- Same for ColBERT backend

### 6. CodeUnit Round-trip (3 tests)
- `test_round_trip_preserves_fields` -- `to_dict()` then `from_dict()` preserves all dataclass fields
- `test_to_dict_returns_plain_dict` -- Output is a dict with expected keys
- `test_from_dict_with_extra_keys_raises` -- Unknown keys cause TypeError

### 7. BackendInfo and BackendStats (5 tests)
- `test_backend_stats_defaults` -- All fields default to 0/""
- `test_backend_info_creation` -- Verify all constructor params
- `test_backend_info_extra_field` -- extra dict passthrough
- `test_faiss_info_returns_correct_backend_name` -- FAISSBackend.info() returns "faiss"
- `test_colbert_info_returns_correct_backend_name` -- ColBERTBackend.info() returns "colbert" with dimension=48

### Bonus: Helper Function Tests (7 tests)
- `_read_index_backend`: none for missing, "faiss"/"colbert" from meta.json, none for bad JSON
- `make_unit_id`: deterministic, different inputs differ, 16-char length

## Results

```
29 passed, 3 warnings in 0.96s
```

All 29 tests pass. The 3 warnings are unrelated SWIG deprecation warnings from the faiss package.
