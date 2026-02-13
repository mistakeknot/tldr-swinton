---
module: ProjectIndex
date: 2026-02-11
problem_type: performance_issue
component: cli
symptoms:
  - "ProjectIndex.build() called 2-4x per CLI command, each scanning all project files"
  - "diff-context --delta triggers 4 separate index builds via symbolkite and difflens"
  - "map_hunks_to_symbols re-scans files with HybridExtractor despite identical data existing in ProjectIndex.symbol_ranges"
root_cause: scope_issue
resolution_type: code_fix
severity: medium
tags: [project-index, shared-state, deduplication, call-chain-threading, performance]
---

# Troubleshooting: Duplicated ProjectIndex Builds Across Engine Calls

## Problem

Every CLI command that uses symbolkite or difflens engines rebuilt `ProjectIndex` from scratch at each engine entry point. A single `diff-context --delta` command triggered 4 separate `ProjectIndex.build()` calls, each scanning all project files, extracting ASTs, and constructing call graphs — multiplying latency by 2-4x.

## Environment
- Module: ProjectIndex / engines layer (symbolkite, difflens, delta)
- Affected Component: CLI commands (`context`, `diff-context`, and their `--delta` variants)
- Date: 2026-02-11

## Symptoms
- `diff-context --delta` triggers 4 index builds: `get_diff_signatures` → `map_hunks_to_symbols` (HybridExtractor scan) + `ProjectIndex.build()`, then `get_diff_context` → `map_hunks_to_symbols` (another scan) + `ProjectIndex.build()` again
- `context --delta` triggers 2 builds: `get_signatures_for_entry` → `ProjectIndex.build()`, then `get_symbol_context_pack` → `ProjectIndex.build()` again
- `map_hunks_to_symbols` duplicates the exact same work as `ProjectIndex.build(include_ranges=True)` by manually scanning files with `HybridExtractor` and computing symbol ranges inline

## What Didn't Work

**Direct solution:** The problem was identified architecturally during plan phase. The call chain analysis showed 4 rebuild points:

```
CLI diff-context --delta
  → delta.get_diff_context_with_delta()
    → difflens.get_diff_signatures()
      → map_hunks_to_symbols()     → HybridExtractor per file  ← BUILD #1
      → ProjectIndex.build()                                    ← BUILD #2
    → difflens.get_diff_context()
      → build_diff_context_from_hunks()
        → map_hunks_to_symbols()   → HybridExtractor per file  ← BUILD #3
        → ProjectIndex.build()                                  ← BUILD #4
```

## Solution

Add a `_project_index: "ProjectIndex | None" = None` optional parameter to 12 functions across the engine/api/CLI layers. Build the index once at the CLI command handler level and thread it through all downstream calls.

**Key pattern — underscore prefix for internal params:**
```python
# Before: each function builds its own index
def get_relevant_context(project, entry_point, depth=2, language="python", ...):
    idx = ProjectIndex.build(project, language, include_sources=True)
    ...

# After: accept pre-built index, build only as fallback
def get_relevant_context(project, entry_point, depth=2, language="python", ...,
                         _project_index: "ProjectIndex | None" = None):
    idx = _project_index or ProjectIndex.build(project, language, include_sources=True)
    ...
```

**Key pattern — fast path in map_hunks_to_symbols:**
```python
def map_hunks_to_symbols(project, hunks, language="python",
                         _project_index=None):
    # Fast path: use pre-built index ranges (no HybridExtractor needed)
    if _project_index and _project_index.symbol_ranges:
        ranges_by_file = defaultdict(list)
        for symbol_id, (s_start, s_end) in _project_index.symbol_ranges.items():
            rel_path = symbol_id.split(":", 1)[0]
            ranges_by_file[rel_path].append((symbol_id, s_start, s_end))
        # ... match hunks to ranges directly
        return results

    # Fallback: original HybridExtractor scan (backward compatible)
    extractor = HybridExtractor()
    ...
```

**Key pattern — build-once in delta engine:**
```python
def get_diff_context_with_delta(project, session_id, ..., _project_index=None):
    # Build once with superset flags
    if _project_index is None:
        _project_index = ProjectIndex.build(
            project, language,
            include_sources=True, include_ranges=True,
            include_reverse_adjacency=True,
        )
    # Thread through both calls
    signatures = get_diff_signatures(..., _project_index=_project_index)
    full_pack = get_diff_context(..., _project_index=_project_index)
```

**Key pattern — CLI builds once at command level:**
```python
# In CLI diff-context handler:
_diff_project_index = ProjectIndex.build(
    project, language,
    include_sources=True, include_ranges=True,
    include_reverse_adjacency=True,
)
# Pass to all downstream calls
pack = get_diff_context_with_delta(..., _project_index=_diff_project_index)
```

**Files modified (6):**
| File | Functions modified |
|------|-------------------|
| `engines/symbolkite.py` | `get_relevant_context`, `get_context_pack`, `get_signatures_for_entry` |
| `engines/difflens.py` | `map_hunks_to_symbols`, `build_diff_context_from_hunks`, `get_diff_signatures`, `get_diff_context` |
| `engines/delta.py` | `get_context_pack_with_delta`, `get_diff_context_with_delta` |
| `api.py` | `get_symbol_context_pack`, `get_diff_context`, `get_signatures_for_entry`, `get_diff_signatures`, `map_hunks_to_symbols`, `build_diff_context_from_hunks` |
| `cli.py` | `context` handler, `diff-context` handler |
| `tests/test_shared_index.py` | 9 new tests (NEW file) |

## Why This Works

1. **Root cause:** Each engine function was self-contained — it built its own `ProjectIndex` without awareness that other functions in the same CLI command would need the same data. This is a classic "scope too narrow" problem where the resource lifetime should match the command lifetime, not the function lifetime.

2. **The `_project_index or ProjectIndex.build(...)` pattern** ensures backward compatibility: external callers who don't pass the parameter get the same behavior as before (each call builds its own index). Only internal orchestration (CLI, delta engine) benefits from sharing.

3. **The `map_hunks_to_symbols` fast path** is especially impactful because it completely eliminates per-file `HybridExtractor.extract()` calls when the index already has `symbol_ranges`. The `_compute_symbol_ranges` logic in both difflens and project_index is identical — the inline version in `map_hunks_to_symbols` was pure duplication.

4. **Building with superset flags** (`include_sources=True, include_ranges=True, include_reverse_adjacency=True`) at the CLI level is harmless — the extra data adds negligible overhead vs. the file scanning + call graph construction that dominates `ProjectIndex.build()` time.

## Prevention

- **When adding new engine functions that need `ProjectIndex`:** Always accept `_project_index` as an optional parameter and use `_project_index or ProjectIndex.build(...)`. Never build unconditionally.
- **When orchestrating multiple engine calls:** Build the index once at the orchestration level with superset flags, then thread it through.
- **Pattern to watch for:** Any function that calls `ProjectIndex.build()`, `HybridExtractor().extract()`, or `iter_workspace_files()` in a loop or repeatedly is likely duplicating work that could be shared.
- **Test pattern:** Use `patch.object(ProjectIndex, "build")` to verify that `build()` is NOT called when `_project_index` is provided.

## Related Issues

No related issues documented yet.
