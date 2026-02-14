# Fix Concurrency Bugs in Semantic Search Backends

**Date:** 2026-02-14
**Priority:** P2
**Status:** Fixed
**Tests:** 398 passed, 0 failed

## Summary

Three concurrency bugs were identified and fixed in the semantic search backend layer: a daemon-level cache race condition, a TOCTOU vulnerability in ColBERT index loading, and a resource leak in the fresh-index build path.

---

## Bug 1: Daemon Cache Race (daemon.py)

### Problem

In `_handle_semantic()`, when `action == "index"`, the code invalidated the cached `_semantic_backend` reference **after** `build_index()` returned:

```python
stats = build_index(str(self.project), ...)
self._semantic_backend = None  # Too late!
```

A concurrent search request arriving during the build would read the stale cached backend and potentially return results from the old index, or worse, hit an inconsistent state if the backend's underlying files were being replaced.

Additionally, the cache check-and-load block for search had no synchronization:

```python
if not hasattr(self, "_semantic_backend") or self._semantic_backend is None:
    self._semantic_backend = get_backend(str(self.project))
    self._semantic_backend.load()
```

Two concurrent search requests could both see `None`, both create backends, and one would be silently discarded (wasting model load time).

### Fix

**File:** `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/daemon.py`

1. Added `import threading` to module imports (line 23).
2. Added `self._semantic_backend = None` and `self._semantic_lock = threading.RLock()` to `__init__` (lines 222-224). Initializing `_semantic_backend` in `__init__` also eliminates the need for the `hasattr()` check.
3. Moved `self._semantic_backend = None` **before** the `build_index()` call, wrapped in `self._semantic_lock`.
4. Wrapped the cache check-and-load block in `with self._semantic_lock:` so only one thread creates the backend.

### Before

```python
# In action == "index":
stats = build_index(...)
self._semantic_backend = None  # After build -- race window

# In action == "search":
if not hasattr(self, "_semantic_backend") or self._semantic_backend is None:
    self._semantic_backend = get_backend(...)  # Unprotected check-and-set
    self._semantic_backend.load()
```

### After

```python
# In action == "index":
with self._semantic_lock:
    self._semantic_backend = None  # Before build -- no stale reads
stats = build_index(...)

# In action == "search":
with self._semantic_lock:
    if self._semantic_backend is None:
        self._semantic_backend = get_backend(...)
        self._semantic_backend.load()
```

---

## Bug 2: Sentinel TOCTOU in ColBERTBackend.load() (colbert_backend.py)

### Problem

The `load()` method checked for a build-in-progress sentinel file without holding the instance lock:

```python
def load(self) -> bool:
    if self._sentinel_path.exists():  # Not under lock!
        self._cleanup_partial()
        return False
```

If another thread was concurrently building (which writes the sentinel at the start of `build()`), the check could race:
- Thread A: `build()` starts, writes sentinel, begins encoding
- Thread B: `load()` checks sentinel, sees it, calls `_cleanup_partial()` which unlinks it
- Thread A: `build()` finishes, removes sentinel (already gone), continues
- Thread B: Returns `False`, caller may retry and load a partially-written index

### Fix

**File:** `/root/projects/tldr-swinton/src/tldr_swinton/modules/semantic/colbert_backend.py`

Wrapped the sentinel check in `with self._instance_lock:` (lines 272-276). The rest of the method (PLAID loading) stays outside the lock since it is expensive and does not need atomicity with the sentinel check.

### Before

```python
def load(self) -> bool:
    if self._sentinel_path.exists():
        self._cleanup_partial()
        return False
```

### After

```python
def load(self) -> bool:
    with self._instance_lock:
        if self._sentinel_path.exists():
            self._cleanup_partial()
            return False
```

---

## Bug 3: plaid-old Cleanup Leak in _build_fresh_index() (colbert_backend.py)

### Problem

In `_build_fresh_index()`, the `plaid-old` directory cleanup happened on the success path only, between the atomic rename and the `retrieve.ColBERT()` call:

```python
try:
    temp_dir.rename(self.index_dir)
    if old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)  # Success path only
    new_retriever = retrieve.ColBERT(index=index)  # Can fail!
    ...
except Exception:
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    raise
```

If `retrieve.ColBERT()` raised an exception after the rename succeeded but before `old_dir` was cleaned up, the `plaid-old` directory would linger indefinitely. Similarly, the except block only cleaned `temp_dir` but not `old_dir`.

### Fix

**File:** `/root/projects/tldr-swinton/src/tldr_swinton/modules/semantic/colbert_backend.py`

1. Moved `old_dir` definition before the `try` block so it is visible in `finally`.
2. Replaced the success-path cleanup and the except-block cleanup with a single `finally` block that cleans up both `old_dir` and `temp_dir` if they still exist.

### Before

```python
try:
    ...
    temp_dir.rename(self.index_dir)
    if old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)
    # retrieve.ColBERT() can fail here, leaving old_dir behind
    ...
except Exception:
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    raise
```

### After

```python
old_dir = self.index_dir.parent / "plaid-old"
try:
    ...
    temp_dir.rename(self.index_dir)
    # No cleanup here -- finally handles it
    ...
except Exception:
    raise
finally:
    if old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
```

---

## Test Results

```
398 passed, 3 warnings in 55.58s
```

All existing tests pass with no regressions. The three warnings are pre-existing (ambiguous entry point disambiguation) and unrelated to these changes.

## Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `src/tldr_swinton/modules/core/daemon.py` | +8 -5 | Add threading import, `_semantic_lock`, fix invalidation order and protect cache load |
| `src/tldr_swinton/modules/semantic/colbert_backend.py` | +12 -8 | Sentinel check under lock, `finally` block for cleanup |
