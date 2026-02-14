# Fix Tempfiles and Exception Handlers — P2 Code Quality

Date: 2026-02-14

## Summary

Three code quality fixes applied to the semantic search backends (`colbert_backend.py`, `faiss_backend.py`, `backend.py`). All 398 tests pass after changes.

## Fix 1: Replace `os.getpid()` with `uuid.uuid4().hex[:8]` in `_write_meta_atomic`

**Problem:** Both `colbert_backend.py` and `faiss_backend.py` used `os.getpid()` as tempfile suffixes in their `_write_meta_atomic()` methods. In a multi-threaded daemon, multiple threads share the same PID, so two concurrent atomic writes could collide on the same temp filename, causing data corruption or race conditions.

**Files changed:**
- `/root/projects/tldr-swinton/src/tldr_swinton/modules/semantic/colbert_backend.py` (line 437): `os.getpid()` -> `uuid.uuid4().hex[:8]`
- `/root/projects/tldr-swinton/src/tldr_swinton/modules/semantic/faiss_backend.py` (line 572): `os.getpid()` -> `uuid.uuid4().hex[:8]`

**Additional change:** Added `import uuid` to the top of both files.

**Rationale:** `uuid.uuid4().hex[:8]` produces a random 8-character hex string unique per call, eliminating any possibility of collision regardless of threading or process reuse.

## Fix 2: Narrow Bare `except Exception` Handlers

**Problem:** Overly broad `except Exception` clauses mask unexpected errors (e.g., `MemoryError`, `AttributeError`, coding bugs) that should propagate rather than being silently caught and treated as recoverable failures.

**Changes:**

### colbert_backend.py
1. **Line 129** (`build()` metadata loading): `except Exception as e:` -> `except (json.JSONDecodeError, KeyError, TypeError) as e:`
   - Only JSON parse errors and missing/wrong-typed dict keys should trigger a rebuild fallback.

2. **Line 300** (`load()`): `except Exception as e:` -> `except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:`
   - Adds `OSError` because `load()` also reads files from disk (PLAID index), which can fail with filesystem errors.

### faiss_backend.py
1. **Line 479** (`load()`): `except Exception as e:` -> `except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:`
   - Same rationale as ColBERT `load()` — JSON parsing + file I/O + dict access.

2. **Line 534** (`_reconstruct_all_vectors` fallback): `except Exception:` -> `except RuntimeError:`
   - FAISS raises `RuntimeError` specifically when `reconstruct_n()` fails (e.g., for certain index types that don't support batch reconstruction). Other exceptions indicate real bugs.

### backend.py
1. **Line 165** (`_read_index_backend()`): `except Exception:` -> `except (json.JSONDecodeError, OSError):`
   - This function only reads a file and parses JSON. The only expected failures are filesystem errors (`OSError`) and malformed JSON (`json.JSONDecodeError`).

## Fix 3: Add `logger.warning` in `_reconstruct_all_vectors`

**Problem:** In `faiss_backend.py`, the `_reconstruct_all_vectors` method silently fell back to per-vector reconstruction when batch reconstruction failed. This hid potentially important diagnostic information.

**Change:** Added `logger.warning("Batch vector reconstruction failed, falling back to per-vector: %s", e)` before the fallback loop.

**Rationale:** The fallback is correct behavior (some FAISS index types don't support `reconstruct_n`), but operators should be aware it's happening since per-vector reconstruction is significantly slower for large indexes.

## Test Results

```
398 passed, 3 warnings in 56.88s
```

All tests pass with no regressions. The 3 warnings are pre-existing (ambiguous symbol disambiguation in test fixtures).

## Files Modified

| File | Changes |
|------|---------|
| `src/tldr_swinton/modules/semantic/colbert_backend.py` | `import uuid`, 2 narrowed exceptions, 1 uuid tempfile fix |
| `src/tldr_swinton/modules/semantic/faiss_backend.py` | `import uuid`, 2 narrowed exceptions, 1 uuid tempfile fix, 1 logger.warning added |
| `src/tldr_swinton/modules/semantic/backend.py` | 1 narrowed exception |
