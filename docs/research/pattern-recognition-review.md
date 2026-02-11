# Pattern Recognition Review: Prompt Cache Optimization Changes

**Date:** 2026-02-10
**Reviewer:** Code Pattern Analysis Expert
**Changes Reviewed:** cache-friendly format implementation

## Executive Summary

The cache-friendly format implementation introduces a new output formatter with strong design patterns, some minor anti-patterns, and good test coverage. The changes are architecturally consistent with existing formatters, though there are opportunities for reducing code duplication.

**Key Findings:**
1. Function signature and structure follows existing formatter patterns well
2. Test organization deviates from codebase conventions (uses test classes vs bare functions)
3. Token estimation function duplicated across two modules
4. Naming conventions are mostly consistent with minor improvements needed

## 1. Design Pattern Analysis

### 1.1 Formatter Pattern Consistency ✅

The `_format_cache_friendly()` function follows the established pattern:

**Pattern conformance:**
- Naming: `_format_<name>(pack: dict) -> str` matches `_format_ultracompact()`, `_format_text_budgeted()`
- Parameter types: Takes `dict` (ContextPack dict) like `_format_context_pack_ultracompact()`
- Return type: Returns `str` consistent with all formatters
- Integration: Properly wired into `format_context_pack()` switch statement

**Architecture:** The formatter correctly handles:
- Empty input (`if not slices: return ...`)
- Delta mode (`unchanged` list detection with `None`/bool/list handling)
- Non-delta mode (graceful fallback when `unchanged=None`)
- Cache stats propagation

**Design strength:** Prefix maximization strategy (putting ALL signatures in prefix, not just unchanged) is innovative and well-documented inline.

### 1.2 Two-Phase Assembly Pattern ✅

The function uses a clever placeholder-replacement pattern:

```python
hints_placeholder = "__CACHE_HINTS_PLACEHOLDER__"
final_parts: list[str] = [header, hints_placeholder, "", prefix_text, breakpoint_line]
# ... assemble output ...
output = "\n".join(final_parts)
# Compute offset from assembled output
breakpoint_offset = output.find("<!-- CACHE_BREAKPOINT")
# Replace placeholder with actual hints
output = output.replace(hints_placeholder, hints_line, 1)
```

This is a **good pattern** because:
- Avoids chicken-and-egg problem (need assembled output to compute offset)
- Single-pass assembly
- Type-safe (no mutation of complex structures)

### 1.3 Deterministic Sorting Pattern ✅

Sorting by symbol ID ensures cache stability:

```python
all_slices = sorted(slices, key=lambda s: s.get("id", ""))
```

This matches the pattern in the old version's prefix section and is critical for byte-exact cache matching.

## 2. Anti-Pattern Detection

### 2.1 Code Duplication: `_estimate_tokens()` ⚠️

**Severity:** Medium
**Location:** `output_formats.py:222` and `contextpack_engine.py:475`

**Duplicate code:**

```python
# output_formats.py
def _estimate_tokens(text_or_lines: str | Iterable[str]) -> int:
    if isinstance(text_or_lines, str):
        text = text_or_lines
    else:
        text = "\n".join(text_or_lines)
    encoder = _get_tiktoken_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)

# contextpack_engine.py
def _estimate_tokens(text: str) -> int:
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        return max(1, len(text) // 4)
```

**Differences:**
1. `output_formats.py` version accepts both `str` and `Iterable[str]`
2. `output_formats.py` uses cached encoder via `_get_tiktoken_encoder()`
3. `contextpack_engine.py` uses bare try/except and no caching

**Impact:**
- Risk of divergent behavior if one is updated without the other
- The cached encoder in `output_formats.py` is more efficient
- The `Iterable[str]` support is more flexible

**Recommendation:** Extract to a shared utility module (`modules/core/token_utils.py`) and import from both locations. Use the `output_formats.py` version as canonical (has caching + flexibility).

### 2.2 Inconsistent None-Checking Pattern ⚠️

**Severity:** Low
**Location:** `contextpack_engine.py:115` (non-delta path)

In the non-delta `build_context_pack()`, cache_stats is always populated:

```python
cache_stats={"hit_rate": 0.0, "hits": 0, "misses": len(slices)}
```

But in `_contextpack_to_dict()`, all delta fields use `is not None` checks:

```python
if pack.unchanged is not None:
    result["unchanged"] = pack.unchanged
if pack.rehydrate is not None:
    result["rehydrate"] = pack.rehydrate
if pack.cache_stats is not None:
    result["cache_stats"] = pack.cache_stats
```

**Issue:** For non-delta packs, `unchanged=None` and `rehydrate=None` are not serialized, but `cache_stats` IS serialized (because it's always populated). This creates an asymmetry.

**Impact:** Minimal. The serialized dict will have `cache_stats` even for non-delta, which is actually correct behavior (cache_stats are meaningful in both modes).

**Recommendation:** Document in `ContextPack` dataclass docstring that `cache_stats` should always be populated (unlike `unchanged`/`rehydrate` which are delta-only).

### 2.3 Magic String Placeholder ⚠️

**Severity:** Very Low
**Location:** `output_formats.py:537`

```python
hints_placeholder = "__CACHE_HINTS_PLACEHOLDER__"
```

**Issue:** Using a string constant that could theoretically appear in user input (unlikely but possible).

**Impact:** Near-zero risk. The placeholder is immediately replaced in the same function, and the chance of a signature containing this exact string is vanishingly small.

**Recommendation:** Consider using a more unique placeholder like `f"__CACHE_HINTS_{id(pack)}__"` if paranoid, but current approach is acceptable.

### 2.4 No Magic Numbers ✅

Token estimates, sorting logic, and all numeric constants are either:
- Derived from data (e.g., `len(all_slices)`)
- Named constants (though none needed here)
- Self-documenting (e.g., `[:16]` for hash prefix is clear in context)

## 3. Naming Convention Analysis

### 3.1 Function Names ✅

All function names follow codebase conventions:

| Function | Pattern | Consistency |
|----------|---------|-------------|
| `_format_cache_friendly` | `_format_<name>` | ✅ Matches `_format_ultracompact`, `_format_text_budgeted` |
| `_estimate_tokens` | `_<verb>_<noun>` | ✅ Matches `_get_tiktoken_encoder`, `_apply_budget` |
| `_contextpack_to_dict` | `_<noun>_to_<noun>` | ✅ Conversion function naming |
| `format_context_pack` | `<verb>_<noun>` | ✅ Public API naming |

### 3.2 Variable Names ✅

Variable naming is clear and consistent:

**Good examples:**
- `all_slices` (descriptive, distinguishes from filtered `dynamic_body_slices`)
- `prefix_parts` / `dynamic_parts` (parallel structure)
- `unchanged_set` (type suffix clarifies it's a set)
- `breakpoint_offset` (intent clear)
- `prefix_hash` (truncated hash, purpose clear)

**Minor improvement opportunity:**
- `hints_placeholder` could be `CACHE_HINTS_PLACEHOLDER` (constant style), but current usage as local variable is acceptable

### 3.3 Test Names ✅

Test method names follow good conventions:

```python
def test_identical_output_across_calls(self):
def test_sorted_by_symbol_id(self):
def test_all_signatures_in_prefix(self):
def test_cache_hints_parseable(self):
```

Pattern: `test_<behavior>_<condition>` or `test_<what>_<how>`

All names are descriptive and telegraph intent.

### 3.4 Class Names ✅

Test classes use descriptive names:

```python
class TestCacheFriendlyDeterminism:
class TestCacheFriendlyPrefixMaximization:
class TestCacheFriendlyNonDelta:
class TestBuildContextPackCacheStats:
class TestCacheFriendlyCLI:
```

Pattern: `Test<Feature><Aspect>`

## 4. Test Structure Analysis

### 4.1 Test Organization: Deviation from Codebase Pattern ⚠️

**Observation:** The new test file uses **test classes**, but existing test files use **bare test functions**.

**Evidence:**

Existing pattern (`test_difflens.py`, `test_context_format.py`):
```python
def test_parse_unified_diff_extracts_ranges() -> None:
    ...

def test_map_hunks_to_symbols(tmp_path: Path) -> None:
    ...
```

New pattern (`test_cache_friendly_format.py`):
```python
class TestCacheFriendlyDeterminism:
    def test_identical_output_across_calls(self):
        ...
```

**Analysis:**

The codebase uses **flat test functions** as the default pattern. Test classes appear to be used rarely or not at all in the existing test suite (based on samples reviewed).

**Pros of test classes:**
- Logical grouping of related tests
- Shared docstrings document test categories
- `pytest` supports both equally well

**Cons:**
- Inconsistent with existing codebase style
- Adds extra indentation level
- Violates principle of least surprise for codebase maintainers

**Impact:** Low. Tests function correctly, but developers expecting flat functions may find the structure unfamiliar.

**Recommendation:** Refactor to flat functions OR add test classes to existing files if this is a new convention. For consistency with reviewed codebase, flat functions are preferred:

```python
def test_cache_friendly_determinism_identical_output():
    """Same input produces byte-identical output every time."""
    ...

def test_cache_friendly_determinism_sorted_by_symbol_id():
    """All slices sorted by symbol ID, not relevance."""
    ...
```

### 4.2 Helper Function Pattern ✅

Helper functions follow good patterns:

```python
def _make_pack(...) -> ContextPack:
    return ContextPack(...)

def _make_slice(...) -> ContextSlice:
    return ContextSlice(...)
```

**Strengths:**
- Named with `_` prefix (private to test module)
- Provide default values for common cases
- Type hints present
- Reduce test boilerplate

**Matches:** Similar pattern used in other test files (e.g., `test_difflens.py` builds test structures inline, but helpers would improve it too).

### 4.3 Test Coverage ✅

The test suite covers:

1. **Determinism:** Byte-exact output across repeated calls ✅
2. **Sorting:** Symbol ID ordering in both prefix and dynamic sections ✅
3. **Prefix maximization:** All signatures in prefix, bodies in dynamic ✅
4. **Cache hints:** JSON structure and parsability ✅
5. **Non-delta mode:** Graceful handling when `unchanged=None` ✅
6. **Edge cases:** Empty slices, signature-only slices ✅
7. **Integration:** CLI end-to-end tests for both `context` and `diff-context` ✅

**Missing coverage (minor):**
- Boolean `unchanged=True` edge case (legacy format)
- Extremely long symbol IDs (line wrapping behavior)
- Non-ASCII characters in symbol names (though likely works fine)

Coverage is **strong** for a new feature.

### 4.4 Test Data Quality ✅

Test data uses realistic patterns:

```python
_make_slice("b.py:changed_fn", "def changed_fn():", "new code", (10, 20))
```

- Realistic symbol IDs (`file.py:symbol_name`)
- Realistic signatures (`def func():`)
- Realistic line ranges
- Descriptive slice IDs telegraph intent (`unchanged_fn`, `changed_fn`)

## 5. Additional Code Quality Observations

### 5.1 Documentation Quality ✅

The `_format_cache_friendly()` docstring is **excellent**:

```python
"""Format context pack for LLM provider prompt caching optimization.

Layout (all content before CACHE_BREAKPOINT is the stable prefix):
1. Header (no timestamps — they'd break byte-exact matching)
2. Cache hints JSON metadata
3. All symbol signatures sorted by symbol ID
4. CACHE_BREAKPOINT marker
5. Changed symbol code bodies sorted by symbol ID
6. Stats footer

Prefix maximization: ALL signatures go in the prefix, even for changed
symbols. Signatures rarely change when only bodies are edited, so this
gives 80-95% cache hit rates in typical edit sessions.
```

**Strengths:**
- Explains the "why" (prefix maximization strategy)
- Documents the layout with numbered sections
- Calls out critical constraints ("no timestamps")
- Quantifies expected benefits ("80-95% cache hit rates")

This is **better documentation** than most existing formatters in the file.

### 5.2 Error Handling ✅

The function handles edge cases gracefully:

```python
if not slices:
    return "# tldrs cache-friendly output\n\n# No symbols to display"
```

Handles three types of `unchanged` values:
```python
if isinstance(unchanged_val, bool):
    unchanged_set: set[str] = set()
elif unchanged_val is None:
    unchanged_set = set()
else:
    unchanged_set = set(unchanged_val)
```

**Pattern:** No exceptions raised for bad input, graceful degradation.

### 5.3 Type Hints ✅

Type hints are present and correct:

```python
def _format_cache_friendly(pack: dict) -> str:
    ...
    unchanged_set: set[str] = set()
    prefix_parts: list[str] = [...]
    dynamic_parts: list[str] = []
```

Inline type annotations help readability in complex functions.

### 5.4 Inline Comments ✅

Inline comments explain non-obvious logic:

```python
# --- Classify slices ---
# --- Build prefix section: ALL signatures ---
# --- Compute prefix metrics ---
# --- Single-pass assembly with placeholder for hints ---
```

Section markers improve navigability in a long function (130 lines).

## 6. Integration Points

### 6.1 CLI Integration ✅

CLI args updated correctly:

```python
"--format",
choices=["text", "ultracompact", "cache-friendly"],
help="Output format (cache-friendly: optimized for LLM provider prompt caching)",
```

Help text explains when to use the format.

### 6.2 ContextPackEngine Integration ✅

Non-delta path now populates `cache_stats`:

```python
return ContextPack(
    slices=slices,
    budget_used=used,
    cache_stats={"hit_rate": 0.0, "hits": 0, "misses": len(slices)},
)
```

This ensures cache-friendly format works in both delta and non-delta modes.

## 7. Comparison with Other Formatters

| Aspect | `_format_cache_friendly` | `_format_ultracompact` | `_format_text_budgeted` |
|--------|-------------------------|------------------------|-------------------------|
| **Input type** | `dict` (ContextPack) | `dict` OR `RelevantContext` | `RelevantContext` |
| **Sorting** | By symbol ID (deterministic) | As-is from input | By depth, index |
| **Budget handling** | Via slice selection (caller) | Via `compute_max_calls()` | Via `_estimate_tokens()` |
| **Section markers** | Explicit (`## CACHE PREFIX`) | Minimal | Hierarchical (`##`, `📍`) |
| **Code formatting** | Fenced (` ``` `) | Fenced (` ``` `) | None (metadata only) |
| **Token estimation** | Used for stats footer | Used for budget | Used for budget |

**Consistency verdict:** Cache-friendly format fits well into the existing formatter family. Differences are justified by the format's unique requirements (determinism, caching).

## 8. Recommendations

### High Priority

1. **Deduplicate `_estimate_tokens()`**
   - Extract to `modules/core/token_utils.py`
   - Use the `output_formats.py` version (cached + flexible)
   - Import from both `output_formats.py` and `contextpack_engine.py`

2. **Test structure consistency**
   - Refactor test classes to flat functions OR
   - Add classes to other test files to establish new convention

### Medium Priority

3. **Document `cache_stats` invariant**
   - Add docstring to `ContextPack.cache_stats` field
   - Note that it should always be populated (unlike `unchanged`/`rehydrate`)

4. **Add type hint to function parameter**
   - Change `pack: dict` to `pack: dict[str, Any]` for clarity
   - Or create a `ContextPackDict` TypedDict

### Low Priority

5. **Consider more unique placeholder**
   - Change `__CACHE_HINTS_PLACEHOLDER__` to include unique ID
   - Only if paranoid about collisions (current approach is fine)

6. **Expand test coverage**
   - Add test for `unchanged=True` (boolean) legacy format
   - Add test for non-ASCII symbol names
   - Add test for extremely long symbol IDs

## 9. Pattern Recognition Summary

### Design Patterns Observed ✅

1. **Formatter Strategy Pattern**: `_format_cache_friendly()` is one of several formatting strategies selected via `format_context_pack(..., fmt="cache-friendly")`
2. **Builder Pattern**: Accumulates output sections in lists (`prefix_parts`, `dynamic_parts`) before final assembly
3. **Template Method**: Follows same structure as other formatters (parse input → build sections → assemble → return string)

### Anti-Patterns Found ⚠️

1. **Code Duplication**: `_estimate_tokens()` in two modules (medium severity)
2. **Inconsistent Style**: Test classes vs flat functions (low severity)
3. **Magic String**: Placeholder constant (very low severity)

### Code Smells: None Detected ✅

No code smells observed:
- No long parameter lists
- No deeply nested conditionals
- No inappropriate intimacy between modules
- No God objects
- No feature envy

## 10. Overall Assessment

**Architecture Quality:** A (Excellent)
- Formatter design is clean and consistent with existing code
- Integration points are well-handled
- Documentation is above average

**Code Quality:** A- (Very Good)
- Implementation is solid with good error handling
- Minor deduplication opportunity with `_estimate_tokens()`
- Type hints and inline comments aid readability

**Test Quality:** B+ (Good)
- Coverage is strong for a new feature
- Test data is realistic
- Structure deviates from codebase convention (classes vs functions)

**Maintainability:** A (Excellent)
- Well-documented with clear docstrings
- Section markers aid navigation
- Naming is consistent and descriptive

**Overall Grade:** A- (Very Good)

The cache-friendly format implementation is high-quality code that fits well into the existing architecture. The main improvements needed are:
1. Deduplicating the token estimation function
2. Aligning test structure with codebase conventions

These are straightforward refactoring tasks that don't diminish the value of the feature implementation.
