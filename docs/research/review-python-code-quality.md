# Python Code Quality Review: Prompt Cache Optimization Plan

**Reviewed by:** Kieran (Senior Python Developer)
**Date:** 2026-02-10
**Plan:** `docs/plans/2026-02-10-prompt-cache-optimization.md`
**Focus:** Implementation code quality (Task 1 tests + Task 2 `_format_cache_friendly()`)

---

## Executive Summary

**Overall Assessment:** PASS with 2 WARNINGS and 3 NOTES

The implementation demonstrates solid Python fundamentals with proper type hints, good test coverage, and clear structure. The two-pass assembly approach for computing `breakpoint_char_offset` has a theoretical edge case that should be addressed. Minor improvements needed around naming consistency and optional parameter handling.

**Key Findings:**
1. Two-pass offset computation has edge case vulnerability (WARNING)
2. Missing type hints in test helper parameters (WARNING)
3. Test naming and structure follows good patterns (PASS)
4. Import organization and code style match existing patterns (PASS)

---

## 1. Implementation Code Review: `_format_cache_friendly()` (Task 2)

### 1.1 Function Signature & Type Hints

**Lines 320-323:**
```python
def _format_cache_friendly(
    pack: dict,
    prefix_sections: list[tuple[str, str]] | None = None,
) -> str:
```

**PASS** - Type hints present for all parameters and return value. Uses modern Python 3.10+ syntax (`|` for union, `list[tuple[str, str]]`).

**NOTE:** The `pack` parameter is typed as `dict` rather than a more specific TypedDict or Protocol. Looking at the existing code (line 438), the current implementation also uses `dict`, so this is consistent with the codebase pattern. However, the codebase has `ContextPack` dataclass available - consider whether a union `ContextPack | dict` would improve type safety in future refactoring.

---

### 1.2 Code Structure & Organization

**Overall Structure:**
```python
# 1. Early return for empty input
# 2. Classify slices (unchanged vs dynamic)
# 3. Build prefix section
# 4. Compute prefix metrics
# 5. Build dynamic section
# 6. Two-pass assembly for breakpoint offset
# 7. Stats footer
```

**PASS** - Clear linear flow with well-separated concerns. Each section is commented and easy to follow. No nested complexity.

**Comparison to Existing Code (lines 438-578):**

The existing `_format_cache_friendly()` has this structure:
```python
# 1. Header + early return
# 2. Separate unchanged (prefix) from changed (dynamic)
# 3. Sort prefix by ID, dynamic by relevance
# 4. Build prefix section (signature-only)
# 5. Build dynamic section (code bodies)
# 6. Assemble with breakpoint marker
# 7. Stats footer
```

**The new implementation follows the same pattern** - this is good consistency. The key differences:
- New: ALL signatures go to prefix (not just unchanged)
- New: Adds cache hints JSON metadata
- New: Adds `prefix_sections` extension point
- New: Two-pass assembly for offset computation

---

### 1.3 Variable Naming

**PASS** - Clear, descriptive names following existing patterns:
- `prefix_parts`, `dynamic_parts` - matches existing `prefix_slices`, `dynamic_slices` pattern
- `prefix_token_est`, `dynamic_token_est` - clear abbreviation, consistent with existing `_est_tokens()`
- `unchanged_set`, `dynamic_body_slices` - self-documenting

**NOTE:** Line 375 uses `entry` for formatting output. The existing code (lines 516, 543) uses the same name. Consistent, but `line` or `formatted_line` would be more explicit about the purpose.

---

### 1.4 Logic Correctness: Slice Classification

**Lines 355-362:**
```python
dynamic_body_slices: list[dict] = []
for item in all_slices:
    symbol_id = item.get("id", "?")
    has_code = item.get("code") is not None
    is_changed = symbol_id not in unchanged_set
    if has_code and is_changed:
        dynamic_body_slices.append(item)
```

**PASS** - Correct logic. Only symbols with both code AND changed status go to dynamic. This matches the requirement: "ALL signatures in prefix, only changed code bodies in dynamic."

**Edge case handled:** Line 348-350 correctly handles `unchanged` being `None`, `[]`, or a boolean by converting to a set. This matches the existing pattern (lines 467-471).

---

### 1.5 Prefix Section Assembly

**Lines 364-391:**
```python
prefix_parts: list[str] = []
prefix_parts.append(f"## CACHE PREFIX ({len(all_slices)} symbols)")
prefix_parts.append("")

for item in all_slices:
    symbol_id = item.get("id", "?")
    signature = item.get("signature", "")
    lines_range = item.get("lines") or []
    line_info = ""
    if lines_range and len(lines_range) == 2:
        line_info = f" @{lines_range[0]}-{lines_range[1]}"
    relevance = item.get("relevance", "")
    unchanged_marker = " [UNCHANGED]" if symbol_id in unchanged_set else ""

    entry = f"{symbol_id} {signature}{line_info} [{relevance}]{unchanged_marker}".strip()
    prefix_parts.append(entry)

prefix_parts.append("")

# Append extra prefix sections from callers (extension point)
if prefix_sections:
    for section_name, section_content in prefix_sections:
        prefix_parts.append(f"## {section_name}")
        prefix_parts.append(section_content)
        prefix_parts.append("")
```

**PASS** - Clean loop with clear formatting. The `prefix_sections` extension point is well-integrated.

**Minor Issue (NOTE):** Line 373 checks `if lines_range and len(lines_range) == 2` - this is correct but defensive. Looking at the existing code (line 511), it uses the same pattern. Consistent, but could use a helper function `_format_line_info(lines_range)` to DRY this up (appears in both prefix and dynamic sections).

---

### 1.6 Dynamic Section Assembly

**Lines 403-421:**
```python
dynamic_parts: list[str] = []
dynamic_token_est = 0

if dynamic_body_slices:
    dynamic_parts.append(f"## DYNAMIC CONTENT ({len(dynamic_body_slices)} changed symbols)")
    dynamic_parts.append("")

    for item in dynamic_body_slices:
        symbol_id = item.get("id", "?")
        signature = item.get("signature", "")
        dynamic_parts.append(f"### {symbol_id}")
        dynamic_parts.append(f"{signature}")
        code = item.get("code", "")
        dynamic_parts.append("```")
        dynamic_parts.extend(code.splitlines())
        dynamic_parts.append("```")
        dynamic_parts.append("")

    dynamic_token_est = _estimate_tokens("\n".join(dynamic_parts))
```

**PASS** - Clean, straightforward. Matches the structure of the existing dynamic section (lines 534-554) but with simplified formatting.

**Difference from existing code:** The existing code includes `line_info` in the dynamic section header (line 538-540). The new code doesn't. This is **intentional** based on the plan's requirement to "minimize dynamic content size" - signatures already appeared in prefix with line info, so omitting it here reduces tokens. **Good optimization.**

---

### 1.7 Two-Pass Offset Computation (CRITICAL SECTION)

**Lines 397-401, 440-465:**
```python
# --- Build cache hints JSON (goes at very top) ---
# We need to know the breakpoint offset, which is:
# len(hints_line) + len(prefix_text) + breakpoint_marker
# Compute after assembly.

# ... (prefix and dynamic assembly) ...

# --- Assemble output ---
# 1. Header line (stable, no timestamp)
header = "# tldrs cache-friendly output v1"

# 2. Prefix
# 3. Breakpoint
breakpoint_line = f"<!-- CACHE_BREAKPOINT: ~{prefix_token_est} tokens -->"

# 4. Dynamic
# 5. Stats

# Build prefix portion (header + prefix_text) to compute offset
prefix_portion = f"{header}\n\n{prefix_text}\n{breakpoint_line}"

# Now we know the breakpoint offset (length of everything before dynamic)
# But we also need to prepend the hints line, which contains the offset...
# Solution: compute offset including the hints line placeholder, then fill it in.
# Use a two-pass approach: first pass without hints to get the offset, then add hints.

# Stable portion = header + hints_line + prefix_text
# hints_line length is approximately stable (hash is always 16 chars, tokens ~4 digits)
# For exact computation, we assemble without hints first:
pre_hints = f"{header}\n\n{prefix_text}\n{breakpoint_line}"
# The hints line will be inserted after the header, so offset = len(hints_line) + len(\n\n) + len(prefix_text) + len(\n) + len(breakpoint_line)

hints_data = {
    "cache_hints": {
        "prefix_tokens": prefix_token_est,
        "prefix_hash": prefix_hash,
        "breakpoint_char_offset": 0,  # placeholder, filled below
        "format_version": 1,
    }
}
hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)

# Final assembly
final_parts: list[str] = [header, hints_line, "", prefix_text, breakpoint_line]
prefix_end = len("\n".join(final_parts))
# Update breakpoint offset in hints
hints_data["cache_hints"]["breakpoint_char_offset"] = prefix_end
hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)
# Reassemble with correct offset
final_parts = [header, hints_line, "", prefix_text, breakpoint_line]
```

**WARNING: Potential Infinite Loop / Instability**

**Problem:** The offset is computed based on the length of `hints_line`, but `hints_line` contains the offset value itself. If changing the offset from N to M causes the hints_line length to change (e.g., from 3 digits to 4 digits: 999 → 1000), the new offset M would be incorrect, requiring another iteration.

**Concrete Example:**
1. First pass: offset = 999, hints_line = `{"cache_hints":{"breakpoint_char_offset":999,...}}` (length: 60)
2. Compute new offset including hints_line: 60 + prefix_text = 1000
3. Second pass: offset = 1000, hints_line = `{"cache_hints":{"breakpoint_char_offset":1000,...}}` (length: 61 - one extra char!)
4. The offset should now be 61 + prefix_text = 1001, but we already fixed it at 1000. **WRONG.**

**Analysis:**
- For offsets < 1000 (3 digits), this is not a problem - the hints_line length doesn't change.
- For offsets at boundaries (999→1000, 9999→10000, etc.), the code produces an off-by-1 error.
- The code does **not** iterate until stable - it only does two passes and assumes the second pass is correct.

**Is this a BLOCKER?**
- The error is 1 character off, which is unlikely to break most LLM cache implementations (they likely have fuzzy matching or don't need byte-exact precision for metadata).
- But it violates the principle of "byte-exact determinism" that the plan emphasizes.
- **Severity: WARNING** (not BLOCKER) - the impact is minimal but the correctness is compromised.

**Fix Recommendation:**
Use a fixed-width format for the offset or iterate until stable:

```python
# Option 1: Fixed-width format (simple, no iteration needed)
hints_data["cache_hints"]["breakpoint_char_offset"] = f"{prefix_end:08d}"  # Always 8 digits

# Option 2: Iterate until stable (more correct but overkill)
for _ in range(5):  # Max 5 iterations to handle digit boundaries
    hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)
    final_parts = [header, hints_line, "", prefix_text, breakpoint_line]
    new_offset = len("\n".join(final_parts))
    if hints_data["cache_hints"]["breakpoint_char_offset"] == new_offset:
        break
    hints_data["cache_hints"]["breakpoint_char_offset"] = new_offset
```

**Recommendation:** Use Option 1 (fixed-width format). It's simpler, more maintainable, and avoids the edge case entirely.

---

### 1.8 hashlib Import

**Line 489 (Task 2, Step 3):**
```
Add `import hashlib` to the top of the file (near the existing imports)
```

**Current imports (lines 1-6):**
```python
"""Context output formatting helpers."""

from __future__ import annotations

import json
from typing import Iterable
```

**PASS** - Adding `import hashlib` after `import json` follows PEP 8 (stdlib imports grouped together, alphabetically sorted). This is the correct location.

**NOTE:** The existing code uses `_get_tiktoken_encoder()` for lazy import of `tiktoken` (lines 203-212). The new code imports `hashlib` at module level. This is fine - `hashlib` is stdlib and always available, while `tiktoken` is an optional dependency. The pattern is appropriate.

---

### 1.9 Pythonic Patterns

**PASS** - The code demonstrates good Pythonic style:
- List comprehensions where appropriate (line 353: `sorted(slices, key=lambda s: s.get("id", ""))`)
- F-strings for formatting (lines 366, 375, 407, 414, etc.)
- `.get()` with defaults for dict access (defensive programming)
- Type hints with modern syntax (`list[str]`, `dict | None`)

**NOTE:** Line 395 computes `prefix_hash = hashlib.sha256(prefix_text.encode("utf-8")).hexdigest()[:16]`. This is correct but not self-documenting. Consider extracting to a helper:

```python
def _compute_prefix_hash(text: str) -> str:
    """Compute stable 16-char SHA256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
```

This would make the intent clearer and be reusable if cache hints expand in the future.

---

### 1.10 Existing Code Consistency

**Comparison to existing `_format_cache_friendly()` (lines 438-578):**

| Aspect | Existing | New | Verdict |
|--------|----------|-----|---------|
| Parameter style | `pack: dict` | `pack: dict, prefix_sections: list[tuple[str, str]] \| None = None` | PASS - extends API cleanly |
| Early return | Line 461-463 | Line 342-343 | PASS - same pattern |
| Sorting | Lines 484, 487-488 | Line 353 | PASS - deterministic sorting maintained |
| Token estimation | `_est_tokens()` (local helper) | `_estimate_tokens()` (module-level) | PASS - uses existing module function |
| Dict access | `.get("key", default)` | Same | PASS |
| String assembly | `lines.append()` then `"\n".join(lines)` | `parts.append()` then `"\n".join(parts)` | PASS - same pattern, different variable names |

**PASS** - The new code follows existing patterns closely. The naming shift from `lines` to `parts` is slightly inconsistent but not problematic.

---

## 2. Test Code Review: `test_cache_friendly_format.py` (Task 1)

### 2.1 Test Helper Functions

**Lines 32-54:**
```python
def _make_pack(
    slices: list[ContextSlice],
    unchanged: list[str] | None = None,
    cache_stats: dict | None = None,
) -> ContextPack:
    return ContextPack(
        slices=slices,
        budget_used=100,
        unchanged=unchanged,
        cache_stats=cache_stats,
    )


def _make_slice(
    id: str,
    signature: str = "def f():",
    code: str | None = None,
    lines: tuple[int, int] | None = None,
    relevance: str | None = "contains_diff",
) -> ContextSlice:
    return ContextSlice(
        id=id, signature=signature, code=code, lines=lines, relevance=relevance
    )
```

**WARNING: Missing Type Hints in Parameters**

- `_make_pack()`: `slices` parameter should be typed as `list[ContextSlice]` - **WAIT, IT IS TYPED.** PASS.
- `_make_slice()`: `id` parameter shadows the builtin `id()` function. This is **bad practice** in Python.

**BLOCKER DOWNGRADED TO WARNING:** While shadowing `id` is poor style, it doesn't break functionality in this context (local parameter scope). However, this should be renamed to `symbol_id` or `slice_id` to match the codebase convention (see line 357, 370, 410 in the implementation - all use `symbol_id`).

**Recommended fix:**
```python
def _make_slice(
    symbol_id: str,  # Changed from 'id'
    signature: str = "def f():",
    code: str | None = None,
    lines: tuple[int, int] | None = None,
    relevance: str | None = "contains_diff",
) -> ContextSlice:
    return ContextSlice(
        id=symbol_id,  # Map to ContextSlice's 'id' field
        signature=signature,
        code=code,
        lines=lines,
        relevance=relevance,
    )
```

---

### 2.2 Test Class Organization

**Classes:**
1. `TestCacheFriendlyDeterminism` (lines 57-102)
2. `TestCacheFriendlyPrefixMaximization` (lines 104-141)
3. `TestCacheHintsMetadata` (lines 143-199)
4. `TestCacheFriendlyPrefixSections` (lines 201-234)
5. `TestCacheFriendlyNonDelta` (lines 236-264)
6. `TestCacheFriendlyEmptyInput` (lines 266-290)
7. `TestBuildContextPackCacheStats` (lines 599-613)
8. `TestCacheFriendlyCLI` (lines 657-698)

**PASS** - Well-organized by feature area. Each class tests a specific aspect of the functionality. Names are clear and follow the `TestFeatureName` convention.

**Comparison to existing test files:**
- `tests/test_contextpack_format.py`: Single test, minimal (11 lines)
- `tests/test_output_caps.py`: Multiple classes, similar organization to the new tests

**The new tests are MORE comprehensive than existing tests** - this is good! The structure matches `test_output_caps.py` which groups related tests into classes.

---

### 2.3 Test Naming

**Sample test names:**
- `test_identical_output_across_calls` (line 60)
- `test_sorted_by_file_path_and_symbol_id` (line 74)
- `test_no_timestamp_in_output` (line 92)
- `test_all_signatures_in_prefix` (line 107)
- `test_code_bodies_only_in_dynamic` (line 125)

**PASS** - Descriptive names that clearly state what is being tested. Follow the `test_<behavior>` convention. Easy to understand at a glance.

**Pythonic naming:** All lowercase with underscores (snake_case), following PEP 8.

---

### 2.4 Assertion Clarity

**Line 72:**
```python
assert out1 == out2, "Output must be byte-identical across calls"
```

**PASS** - Clear assertion with descriptive error message.

**Lines 119-123:**
```python
bp_idx = out.find("CACHE_BREAKPOINT")
assert bp_idx > 0, "No CACHE_BREAKPOINT found"
prefix = out[:bp_idx]
assert "unchanged_fn" in prefix, "Unchanged sig missing from prefix"
assert "changed_fn" in prefix, "Changed sig missing from prefix"
```

**PASS** - Defensive: verifies preconditions before testing the actual behavior. Good error messages.

**Lines 168-181 (JSON parsing test):**
```python
for line in out.split("\n"):
    if "cache_hints" in line:
        hints = json.loads(line)
        assert "cache_hints" in hints
        h = hints["cache_hints"]
        assert "prefix_tokens" in h
        assert "prefix_hash" in h
        assert "breakpoint_char_offset" in h
        assert isinstance(h["prefix_tokens"], int)
        assert isinstance(h["prefix_hash"], str)
        assert isinstance(h["breakpoint_char_offset"], int)
        assert h["prefix_tokens"] > 0
        return
raise AssertionError("No parseable cache_hints JSON line found")
```

**PASS** - Thorough validation of the JSON structure. Tests both presence and types of fields. The fallback `raise AssertionError` ensures the test fails if the JSON line is missing entirely.

**NOTE:** This pattern (find-parse-validate) appears in multiple tests (lines 168-181, 192-198). Could be extracted to a helper:

```python
def _extract_cache_hints(output: str) -> dict:
    """Extract and parse cache_hints JSON from output."""
    for line in output.split("\n"):
        if "cache_hints" in line:
            hints = json.loads(line)
            assert "cache_hints" in hints
            return hints["cache_hints"]
    raise AssertionError("No parseable cache_hints JSON line found")
```

Then tests become:
```python
hints = _extract_cache_hints(out)
assert "prefix_tokens" in hints
assert isinstance(hints["prefix_tokens"], int)
```

This would reduce duplication and improve maintainability.

---

### 2.5 Fixture Design

**Lines 663-666 (tmp_path fixture):**
```python
def test_context_cache_friendly(self, tmp_path):
    """tldrs context --format cache-friendly produces valid output."""
    f = tmp_path / "sample.py"
    f.write_text("def hello():\n    return 'world'\n\ndef goodbye():\n    return 'bye'\n")
```

**PASS** - Uses pytest's built-in `tmp_path` fixture correctly. Creates minimal test data inline rather than in a separate fixture. This is appropriate for simple tests.

**Lines 677-688 (git repo setup):**
```python
def test_diff_context_cache_friendly(self, tmp_path):
    """tldrs diff-context --format cache-friendly with delta info."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
    f = tmp_path / "a.py"
    f.write_text("def a():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
    f.write_text("def a():\n    return 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "change"], cwd=tmp_path, capture_output=True)
```

**PASS** - Matches the existing pattern in `test_output_caps.py` (lines 145-156). The git setup is verbose but necessary for diff-context testing.

**NOTE:** This git setup pattern is duplicated from `test_output_caps.py`. Consider extracting to a shared fixture in `conftest.py`:

```python
@pytest.fixture
def git_repo_with_change(tmp_path):
    """Create a git repo with an initial commit and a change."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

    f = tmp_path / "a.py"
    f.write_text("def a():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    f.write_text("def a():\n    return 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "change"], cwd=tmp_path, capture_output=True)

    return tmp_path
```

This would DRY up both `test_cache_friendly_format.py` and `test_output_caps.py`.

---

### 2.6 Test Coverage

**Requirements from the plan:**
1. ✅ Deterministic output (lines 60-72, 92-102)
2. ✅ Sorted by file path and symbol ID (lines 74-90)
3. ✅ All signatures in prefix (lines 107-123)
4. ✅ Code bodies only in dynamic (lines 125-141)
5. ✅ Cache hints JSON metadata (lines 146-199)
6. ✅ Prefix sections extension point (lines 204-233)
7. ✅ Non-delta path (lines 239-262)
8. ✅ Empty input edge cases (lines 269-289)
9. ✅ CLI integration (lines 663-698)

**PASS** - Comprehensive coverage of all features and edge cases.

---

### 2.7 Existing Test Patterns

**Comparison to `test_output_caps.py`:**

| Pattern | test_output_caps.py | New tests | Match? |
|---------|---------------------|-----------|--------|
| Classes for grouping | Yes (lines 17-90) | Yes | ✅ |
| Unit + integration | Yes (unit: 17-122, CLI: 124-165) | Yes (unit: 57-613, CLI: 657-698) | ✅ |
| Helper functions | Yes (`_content_before_marker`, line 12-13) | Yes (`_make_pack`, `_make_slice`) | ✅ |
| Subprocess.run for CLI | Yes (lines 134-165) | Yes (lines 667-698) | ✅ |
| tmp_path fixture | Yes (line 127) | Yes (line 663) | ✅ |

**PASS** - The new tests follow the same patterns as existing tests. Good consistency.

---

## 3. Cross-Cutting Concerns

### 3.1 Error Handling

**Implementation (lines 342-343):**
```python
if not slices:
    return "# tldrs cache-friendly output\n\n# No symbols to display"
```

**PASS** - Graceful handling of empty input. Matches existing pattern (line 462).

**Test coverage (line 270-272):**
```python
def test_empty_slices(self):
    pack = _make_pack(slices=[])
    out = format_context_pack(pack, fmt="cache-friendly")
    assert "No symbols" in out
```

**PASS** - Edge case tested.

---

### 3.2 Extensibility

**`prefix_sections` parameter (lines 322, 384-389):**

**PASS** - Clean extension point. The optional parameter with `None` default doesn't break existing callers. The implementation correctly handles both `None` and empty list (lines 385-389).

**Test coverage (lines 204-233):**

**PASS** - Both positive (custom section appears) and negative (empty list = no change) cases tested.

---

### 3.3 Documentation

**Docstring (lines 324-339):**
```python
"""Format context pack for LLM provider prompt caching optimization.

Layout (all content before CACHE_BREAKPOINT is the stable prefix):
1. Cache hints JSON metadata
2. All symbol signatures sorted by (file_path, symbol_id)
3. Optional extra prefix_sections
4. CACHE_BREAKPOINT marker
5. Changed symbol code bodies sorted by (file_path, symbol_id)
6. Stats footer

Args:
    pack: ContextPack dict with slices, unchanged list, etc.
    prefix_sections: Optional extra (name, content) tuples for the prefix.

Returns:
    Formatted string with cache-friendly structure.
"""
```

**PASS** - Clear, comprehensive docstring. Explains the layout, parameters, and return value. The numbered list makes the structure easy to understand.

**Comparison to existing docstring (lines 439-454):**

The existing docstring is less detailed (doesn't explain the layout step-by-step). **The new docstring is BETTER.**

---

## 4. Summary of Issues

### BLOCKERS: 0

None. The code is functional and meets the plan's requirements.

---

### WARNINGS: 2

#### WARNING 1: Two-Pass Offset Computation Edge Case
**Location:** Task 2, lines 440-465
**Issue:** The `breakpoint_char_offset` computation assumes changing the offset value doesn't change the hints_line length. At digit boundaries (999→1000, 9999→10000), this produces an off-by-1 error.
**Impact:** Low (1 char off in a metadata field is unlikely to break LLM caching).
**Fix:** Use fixed-width format (`f"{offset:08d}"`) or iterate until stable.
**Code:**
```python
# Current (two-pass, unstable at boundaries):
prefix_end = len("\n".join(final_parts))
hints_data["cache_hints"]["breakpoint_char_offset"] = prefix_end
hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)
final_parts = [header, hints_line, "", prefix_text, breakpoint_line]

# Recommended fix (fixed-width):
hints_data["cache_hints"]["breakpoint_char_offset"] = 0  # placeholder
hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)
final_parts = [header, hints_line, "", prefix_text, breakpoint_line]
prefix_end = len("\n".join(final_parts))
hints_data["cache_hints"]["breakpoint_char_offset"] = f"{prefix_end:08d}"  # Always 8 digits, stable
hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)
final_parts = [header, hints_line, "", prefix_text, breakpoint_line]
```

---

#### WARNING 2: Test Helper Shadows Builtin `id()`
**Location:** Task 1, line 46
**Issue:** `_make_slice()` parameter `id` shadows Python's builtin `id()` function.
**Impact:** Low (local scope, no practical conflict, but poor style).
**Fix:** Rename to `symbol_id` to match implementation convention.
**Code:**
```python
# Current:
def _make_slice(
    id: str,  # Shadows builtin
    signature: str = "def f():",
    ...
) -> ContextSlice:
    return ContextSlice(id=id, ...)

# Recommended:
def _make_slice(
    symbol_id: str,  # Clear, no shadowing
    signature: str = "def f():",
    ...
) -> ContextSlice:
    return ContextSlice(id=symbol_id, ...)
```

---

### NOTES: 3

#### NOTE 1: Missing TypedDict for `pack` Parameter
**Location:** Task 2, line 321
**Issue:** `pack: dict` is too generic. The existing code uses the same pattern, but type safety would improve with a TypedDict or `ContextPack | dict` union.
**Impact:** None (consistent with existing code).
**Recommendation:** Future refactoring - define `ContextPackDict` TypedDict for better IDE support and type checking.

---

#### NOTE 2: Duplicated Line Info Formatting Logic
**Location:** Task 2, lines 373-375 (prefix), 413 (dynamic)
**Issue:** The pattern `if lines_range and len(lines_range) == 2: line_info = f" @{...}"` appears twice. Could be extracted to a helper.
**Impact:** Minor duplication (~3 lines).
**Recommendation:** Extract to `_format_line_info(lines_range: list[int] | None) -> str` if adding more format variations in the future.

---

#### NOTE 3: Test Fixture Duplication
**Location:** Task 1, lines 677-688; `test_output_caps.py` lines 145-156
**Issue:** Git repo setup pattern is duplicated across two test files.
**Impact:** Maintenance burden if the setup needs to change.
**Recommendation:** Extract to shared fixture in `conftest.py` as `git_repo_with_change(tmp_path)`.

---

## 5. Verdict

**PASS** with conditions:

1. **Fix WARNING 1** (two-pass offset) before merging - use fixed-width format.
2. **Fix WARNING 2** (test helper naming) before merging - rename `id` to `symbol_id`.
3. **Address NOTES 1-3** in future refactoring (not blockers for this PR).

The code demonstrates **strong Python fundamentals**: proper type hints, clean structure, good test coverage, and consistency with existing patterns. The two warnings are edge cases that should be addressed to maintain the plan's "byte-exact determinism" guarantee, but they don't block functionality.

---

## 6. Positive Highlights

**What this code does WELL:**

1. **Type hints everywhere** - All functions have proper signatures with modern Python 3.10+ syntax.
2. **Clear structure** - Each section is well-commented and easy to follow.
3. **Comprehensive tests** - 8 test classes covering happy path, edge cases, and CLI integration.
4. **Consistent with codebase** - Follows existing patterns for sorting, dict access, string assembly.
5. **Good docstrings** - The new `_format_cache_friendly()` docstring is clearer than the existing one.
6. **Defensive programming** - Handles `None`, empty lists, missing keys gracefully.
7. **Extension point** - `prefix_sections` parameter is cleanly integrated and well-tested.

This is **high-quality Python code** that any senior developer would be proud to merge (after fixing the two warnings).

---

## Appendix: Related Existing Code Patterns

### Pattern 1: Dict Access with Defaults
**Everywhere in both existing and new code:**
```python
symbol_id = item.get("id", "?")
signature = item.get("signature", "")
```
**Verdict:** ✅ Consistent

### Pattern 2: Token Estimation
**Existing (line 491-495):**
```python
def _est_tokens(text: str) -> int:
    encoder = _get_tiktoken_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)
```
**New (line 394):**
```python
prefix_token_est = _estimate_tokens(prefix_text)
```
**Verdict:** ✅ Uses existing module-level function (better than local helper)

### Pattern 3: Empty Input Handling
**Existing (line 461-463):**
```python
if not slices:
    lines.append("# No symbols to display")
    return "\n".join(lines)
```
**New (line 342-343):**
```python
if not slices:
    return "# tldrs cache-friendly output\n\n# No symbols to display"
```
**Verdict:** ✅ Same pattern, slightly different header text

---

**End of Review**
