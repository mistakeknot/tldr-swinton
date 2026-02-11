# Simplification Analysis: Prompt Cache Optimization Plan

**Reviewed:** 2026-02-10
**Plan:** `docs/plans/2026-02-10-prompt-cache-optimization.md`
**Existing Code:** `src/tldr_swinton/modules/core/output_formats.py:438-578`

## Core Purpose

The code needs to format context packs for LLM prompt caching by:
1. Putting stable content (signatures) before a CACHE_BREAKPOINT marker
2. Putting dynamic content (code bodies) after the marker
3. Ensuring deterministic ordering so the same input produces byte-identical output
4. Providing metadata to help consumers optimize cache hit rates

## Unnecessary Complexity Found

### 1. BLOCKER: Two-Pass Breakpoint Offset Assembly (Lines 397-465)

**Issue:** The plan proposes a two-pass approach to compute `breakpoint_char_offset`:
- First pass: assemble without hints to measure
- Second pass: insert hints with computed offset, reassemble

**Why it's unnecessary:**

The offset serves ONE purpose: tell consumers where the breakpoint is. But there's a simpler alternative:

```python
# After full assembly is complete:
full_output = "\n".join(final_parts)
breakpoint_offset = full_output.find("CACHE_BREAKPOINT")
# Then emit it in metadata or let consumers compute it themselves
```

**Even simpler:** Don't compute it at all. Consumers can compute the offset from the marker position:

```python
# Consumer code (trivial):
offset = output.find("CACHE_BREAKPOINT")
```

The marker already exists for human and machine parsing. The offset is redundant information that can be computed in O(n) time from the string. Computing it during assembly adds complexity (two passes) for zero functional benefit.

**Impact:**
- **LOC saved:** ~20 lines (lines 398-465 collapse to single pass)
- **Complexity reduction:** Eliminate nested assembly logic
- **Performance:** Avoid double-join of potentially large string arrays

**Recommended action:** Remove `breakpoint_char_offset` from cache hints entirely. If consumers need it, they can call `.find("CACHE_BREAKPOINT")` in 1 line of code.

**Alternative if offset is required:** Compute it AFTER final assembly with a single `.find()` call, not during assembly.

---

### 2. WARNING: prefix_sections Extension Point (Lines 202-221, 323-337, 385-390)

**Issue:** The plan adds `prefix_sections: list[tuple[str, str]] | None` parameter to support future features like import compression and bundles. This is tested in `TestCacheFriendlyPrefixSections` (35 lines) but NO feature uses it today.

**YAGNI violation:** Adding extension points without a concrete use case is premature. The cited features (import compression, bundles) are roadmap items that may never be implemented, or may need a different API when they are.

**Actual cost:**
- Parameter in function signature (increases cognitive load for all callers)
- Loop to render sections (lines 385-390: 6 lines)
- Test class with 2 test methods (35 lines)
- Documentation overhead in docstring

**When to add it:** When the FIRST consumer actually needs it. At that point you'll know:
- What data format makes sense (might not be `(name, content)` tuples)
- Where in the output it belongs (might not be after signatures)
- Whether multiple consumers need different things (might need multiple hooks)

**Example from existing code:** The current `_format_cache_friendly()` has ZERO extension points but is perfectly serviceable. Adding one "just in case" violates the project's stated YAGNI principle.

**Impact:**
- **LOC saved:** ~6 lines in implementation + ~35 lines in tests = 41 lines
- **Complexity reduction:** Simpler function signature, one less concept to understand
- **Maintenance burden:** Every future refactor must consider this unused parameter

**Recommended action:** Delete `prefix_sections` parameter. Add it in a future PR when a feature actually needs it (with a test that uses the feature, not a synthetic test).

---

### 3. NOTE: Redundant Empty Check (Lines 341-343)

**Issue:**
```python
slices = pack.get("slices", [])
if not slices:
    return "# tldrs cache-friendly output\n\n# No symbols to display"
```

This is fine, but immediately after (lines 345-362) there's a loop that classifies slices, followed by section building that handles empty lists gracefully:

- `prefix_slices` can be empty → "## CACHE PREFIX" section just doesn't render (lines 501-519)
- `dynamic_slices` can be empty → "## DYNAMIC CONTENT" section doesn't render (lines 527-555)

**Why it might be unnecessary:** If both lists are empty, the output would be a header + stats footer, which is arguably more useful than "No symbols to display" (it shows what happened).

**Counter-argument:** The early return provides a clear "nothing to do" signal and avoids computing token estimates for empty sections.

**Decision:** KEEP the early return. It's 3 lines and provides clear error handling. This is NOT unnecessary complexity.

---

### 4. NOTE: Duplicate Token Estimation Logic (Lines 491-495, 215-224)

**Issue:** The plan defines a nested `_est_tokens()` helper inside `_format_cache_friendly()` that duplicates the module-level `_estimate_tokens()` function.

**Why this exists:** The nested version is identical but defined inline to avoid scope issues or for convenience.

**Is this unnecessary?**

Compare:
```python
# Proposed (lines 491-495):
def _est_tokens(text: str) -> int:
    encoder = _get_tiktoken_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)

prefix_token_est = _est_tokens(prefix_text)
```

vs. existing:
```python
prefix_token_est = _estimate_tokens(prefix_text)  # Call module-level function
```

**Verdict:** The nested function is UNNECESSARY. Just call `_estimate_tokens()` directly (already exists in the module). The nested version adds 6 lines and a duplicate implementation.

**Impact:**
- **LOC saved:** 6 lines (delete nested function definition)
- **DRY violation:** Remove code duplication

**Recommended action:** Use the existing `_estimate_tokens()` instead of defining `_est_tokens()` inline.

---

### 5. WARNING: Separate Token Variables for Each Section (Lines 499, 525, 567)

**Issue:** The code computes `prefix_token_est` and `dynamic_token_est` separately, then adds them at the end:

```python
prefix_token_est = _estimate_tokens(prefix_text)  # Line 521
dynamic_token_est = _estimate_tokens(dynamic_text)  # Line 555
total_tokens = prefix_token_est + dynamic_token_est  # Line 567
```

**Is this necessary?** It depends on whether consumers need the breakdown.

**Use case check:**
- The STATS footer shows "Prefix ~X tokens | Dynamic ~Y tokens | Total ~Z tokens"
- The cache_hints JSON includes `prefix_tokens` (for Anthropic/OpenAI cache size estimation)

**Verdict:** The breakdown IS used in output, so these variables are NECESSARY. This is not over-engineering.

---

### 6. BLOCKER: Task 3 is a One-Line Fix Masquerading as a Task

**Issue:** Task 3 ("Fix Non-Delta Path in `format_context()`") is described as:

> Key change: `"unchanged": None` instead of `[]`, and populate `cache_stats`.

The actual change (lines 89, 538-543):
```python
# Before:
"unchanged": [],

# After:
"unchanged": None,
"cache_stats": {
    "hit_rate": 0.0,
    "hits": 0,
    "misses": len(ctx.functions),
},
```

This is a **5-line edit** in a function that's being completely rewritten in Task 2 anyway.

**Why is this a separate task?**
- It's in a different function (`format_context()` vs. `_format_cache_friendly()`)
- But it's part of the same feature (non-delta support)

**YAGNI check:** Does this need a separate commit? No.

**Recommended action:** Fold Task 3 into Task 2. It's the same atomic feature ("support non-delta mode in cache-friendly format"). Splitting it into two tasks/commits adds process overhead for no clarity benefit.

**Impact:**
- **LOC saved:** 0 (code is still needed)
- **Process simplification:** 5 tasks → 4 tasks, fewer commits, simpler history

---

### 7. NOTE: Task 4 Also Feels Small

**Issue:** Task 4 adds `cache_stats` to `build_context_pack()`:

```python
cache_stats={"hit_rate": 0.0, "hits": 0, "misses": len(slices)},
```

This is a **1-line change** (plus a test).

**Why is this a separate task?**
- It touches a different file (`contextpack_engine.py` vs. `output_formats.py`)
- It's about populating data, not formatting

**Is this YAGNI?** No, this is necessary — the non-delta path needs cache_stats to avoid crashes/errors when `_format_cache_friendly()` tries to read it.

**Is it worth a separate task?** Marginally. It's in a different module, so separate commit makes sense for bisect/blame clarity.

**Verdict:** KEEP as separate task (unlike Task 3), but consider combining with Task 3 if Task 3 is kept separate.

---

## Code to Remove

### From Proposed Implementation:

| Location | Lines | Reason | LOC Saved |
|----------|-------|--------|-----------|
| lines 398-465 | ~68 | Two-pass breakpoint offset computation (use `.find()` after assembly) | 50 |
| lines 491-495 | 6 | Nested `_est_tokens()` duplicates existing `_estimate_tokens()` | 6 |
| lines 322-337, 385-390 | ~20 | `prefix_sections` parameter and tests (YAGNI) | 20 |
| Task 3 | N/A | Fold into Task 2 (same feature) | 0 code, 1 task saved |

**Total potential LOC reduction:** ~76 lines in implementation + ~35 lines in tests = **111 lines (~20% of plan)**

---

## Simplification Recommendations

### 1. HIGHEST IMPACT: Remove Two-Pass Assembly

**Current (proposed lines 397-465):**
```python
# First pass without hints to compute offset
pre_hints = f"{header}\n\n{prefix_text}\n{breakpoint_line}"

hints_data = {
    "cache_hints": {
        "prefix_tokens": prefix_token_est,
        "prefix_hash": prefix_hash,
        "breakpoint_char_offset": 0,  # placeholder
        "format_version": 1,
    }
}
hints_line = json.dumps(hints_data, ...)

# Assemble to compute offset
final_parts: list[str] = [header, hints_line, "", prefix_text, breakpoint_line]
prefix_end = len("\n".join(final_parts))

# Second pass: update hints and reassemble
hints_data["cache_hints"]["breakpoint_char_offset"] = prefix_end
hints_line = json.dumps(hints_data, ...)
final_parts = [header, hints_line, "", prefix_text, breakpoint_line]
```

**Proposed (simplest):**
```python
# Option A: Don't compute it — let consumers call .find("CACHE_BREAKPOINT")
hints_data = {
    "cache_hints": {
        "prefix_tokens": prefix_token_est,
        "prefix_hash": prefix_hash,
        # No breakpoint_char_offset field
        "format_version": 1,
    }
}
hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)

# Single assembly pass
final_parts: list[str] = [header, hints_line, "", prefix_text, breakpoint_line]
```

**Proposed (if offset is required):**
```python
# Option B: Compute it AFTER assembly, not during
final_parts: list[str] = [header, hints_line_placeholder, "", prefix_text, breakpoint_line, ...]
output = "\n".join(final_parts)

# Now compute offset
offset = output.find("CACHE_BREAKPOINT")

# Replace placeholder hints with correct offset
hints_data["cache_hints"]["breakpoint_char_offset"] = offset
hints_line = json.dumps(hints_data, ...)
output = output.replace(hints_line_placeholder, hints_line, 1)
```

**Impact:**
- LOC saved: ~50 lines
- Clarity: Single assembly pass is much easier to understand
- Performance: No double-join of potentially large arrays

---

### 2. HIGH IMPACT: Delete prefix_sections Extension Point

**Current (proposed):**
```python
def _format_cache_friendly(
    pack: dict,
    prefix_sections: list[tuple[str, str]] | None = None,  # ← DELETE THIS
) -> str:
    ...
    # Append extra prefix sections from callers (extension point)
    if prefix_sections:  # ← DELETE THIS BLOCK (6 lines)
        for section_name, section_content in prefix_sections:
            prefix_parts.append(f"## {section_name}")
            prefix_parts.append(section_content)
            prefix_parts.append("")
```

**Proposed:**
```python
def _format_cache_friendly(pack: dict) -> str:
    # No prefix_sections parameter
    # No conditional rendering of extra sections
```

Also delete test class `TestCacheFriendlyPrefixSections` (35 lines).

**Impact:**
- LOC saved: 41 lines
- Simpler API
- Easier to understand what the function does

**When to add it back:** When a feature needs it. At that point the test will be a real feature test, not a synthetic "can we pass data through?" test.

---

### 3. MEDIUM IMPACT: Use Existing _estimate_tokens()

**Current (proposed lines 491-495):**
```python
def _est_tokens(text: str) -> int:
    encoder = _get_tiktoken_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)
```

**Proposed:**
```python
# Delete the nested function, use the existing module-level function:
prefix_token_est = _estimate_tokens(prefix_text)
dynamic_token_est = _estimate_tokens(dynamic_text)
```

**Impact:**
- LOC saved: 6 lines
- DRY principle

---

### 4. MEDIUM IMPACT: Merge Task 3 into Task 2

**Current plan:**
- Task 2: Rewrite `_format_cache_friendly()`
- Task 3: Fix non-delta path in `format_context()`

**Proposed:**
- Task 2: Rewrite cache-friendly format (both functions)

**Rationale:** They're the same feature ("non-delta support"). The Task 2 commit message already says "rewrite cache-friendly format with prefix maximization" — adding 5 lines to `format_context()` doesn't change the scope.

**Impact:**
- Fewer commits
- Clearer history (one commit = one feature)
- Less context switching during implementation

---

### 5. LOW IMPACT: Simplify Sort Keys

**Current (proposed line 353):**
```python
all_slices = sorted(slices, key=lambda s: s.get("id", ""))
```

**Observation:** The plan says "sorted by (file_path, symbol_id)" but the code sorts by `id` alone. The `id` field already contains `file_path:symbol_id` (see format: `a.py:alpha`), so this is correct.

**However:** If `id` is missing, it defaults to `""`, which sorts before valid IDs. Is this the right behavior?

**Alternative:**
```python
all_slices = sorted(slices, key=lambda s: s.get("id", "zzz"))  # Missing IDs sort last
```

**Verdict:** This is a minor edge case. Current behavior is probably fine (missing IDs should be rare). Don't change unless it causes problems.

---

## YAGNI Violations

### 1. prefix_sections Extension Point

**Why it violates YAGNI:**
- No feature uses it today
- Cited use cases (import compression, bundles) are roadmap items
- Adding it now means maintaining it forever, even if those features never materialize

**What to do instead:**
- Delete it
- When a feature needs it, add it with a test that exercises the feature (not a synthetic test)

---

### 2. breakpoint_char_offset Field

**Why it might violate YAGNI:**
- Consumers can compute this in 1 line: `offset = output.find("CACHE_BREAKPOINT")`
- The marker already exists for parsing
- Computing it during assembly adds complexity (two passes) for marginal convenience

**Counter-argument:** It's useful for consumers who want to skip parsing. But is that a real use case? The plan doesn't cite one.

**Recommendation:** If no consumer needs it, delete it. If consumers need it, compute it AFTER assembly (simpler implementation).

---

## Test Suite Simplification

### Current (proposed): 9 test classes, ~290 lines

1. `TestCacheFriendlyDeterminism` (3 tests) ← KEEP
2. `TestCacheFriendlyPrefixMaximization` (2 tests) ← KEEP
3. `TestCacheHintsMetadata` (3 tests) ← MERGE with class 2
4. `TestCacheFriendlyPrefixSections` (2 tests) ← DELETE (tests unused feature)
5. `TestCacheFriendlyNonDelta` (2 tests) ← KEEP
6. `TestBuildContextPackCacheStats` (1 test) ← KEEP but move to contextpack tests
7. `TestCacheFriendlyEmptyInput` (2 tests) ← MERGE with class 1 (edge cases)
8. `TestCacheFriendlyCLI` (2 tests) ← KEEP

**Proposed: 5 test classes**

1. **TestCacheFriendlyBasics** (determinism, sorting, empty input, no timestamps)
2. **TestCacheFriendlyPrefixMaximization** (all sigs in prefix, code in dynamic, cache hints JSON)
3. **TestCacheFriendlyNonDelta** (non-delta path)
4. **TestBuildContextPackCacheStats** (in `test_contextpack_engine.py` where it belongs)
5. **TestCacheFriendlyCLI** (e2e)

**Impact:**
- Test count: same (~15 tests)
- LOC saved: ~50 lines (mostly from deleting prefix_sections tests)
- Clarity: Related tests grouped together

**Rationale:**
- Determinism + edge cases belong together (both test basic correctness)
- Prefix maximization + cache hints belong together (both test cache optimization features)
- `TestBuildContextPackCacheStats` tests a ContextPackEngine feature, not a format feature

---

## Dead Code Paths

### In Proposed Implementation:

None found. The logic is straightforward:
1. Separate slices into prefix (all) and dynamic (changed with code)
2. Sort deterministically
3. Render sections
4. Assemble output

### In Task Plan:

- Task 3 as separate task (fold into Task 2)
- prefix_sections code paths (delete, unused)

---

## Unnecessary Variables

### In Proposed Implementation:

Most variables are necessary for readability:
- `all_slices`, `dynamic_body_slices` — clear separation of concerns
- `prefix_parts`, `dynamic_parts` — staged assembly
- `prefix_token_est`, `dynamic_token_est` — used in output

One questionable variable:
- `pre_hints` (line 445) — only used once, in a computation that should be deleted anyway

**Verdict:** If two-pass assembly is removed, this variable disappears.

---

## Final Assessment

### Complexity Score: MEDIUM-HIGH

The plan adds useful features (deterministic caching, prefix maximization) but includes unnecessary complexity:
- Two-pass assembly for breakpoint offset (BLOCKER)
- Unused extension point (WARNING)
- Duplicate token estimation logic (NOTE)
- Extra task for 5-line change (WARNING)

### Total Potential LOC Reduction: ~111 lines (~20% of plan)

- Implementation: 76 lines
- Tests: 35 lines

### Recommended Action: PROCEED WITH SIMPLIFICATIONS

The core feature (cache-friendly format) is valuable. The simplifications above make it:
- **Simpler:** Single-pass assembly, no unused extension points
- **More maintainable:** Fewer LOC, DRY principle
- **Faster:** No double-join of output

**Priority order:**
1. **BLOCKER:** Remove two-pass assembly (or use post-assembly `.find()`)
2. **WARNING:** Delete `prefix_sections` extension point
3. **WARNING:** Merge Task 3 into Task 2
4. **NOTE:** Use existing `_estimate_tokens()` instead of nested function
5. **NOTE:** Simplify test structure (5 classes instead of 9)

### Estimated Impact After Simplifications:

- Total implementation LOC: ~120 lines (down from ~196 in plan)
- Test LOC: ~200 lines (down from ~290 in plan)
- Tasks: 4 (down from 5)
- Complexity: LOW (single-pass, no YAGNI violations)

---

## Comparison to Existing Code

The existing `_format_cache_friendly()` (lines 438-578) is **141 lines**. The proposed rewrite is **147 lines** (net +6 lines) but adds:
- Deterministic sorting
- Cache hints JSON
- Prefix maximization (all signatures, not just unchanged)
- prefix_sections extension point (unused)
- Two-pass assembly (unnecessary)

**After simplifications:** ~120 lines (net -21 lines) with all the useful features and none of the bloat.

**Verdict:** The simplified version is BETTER than the existing code — more features, fewer lines, simpler logic.

---

## Appendix: Line-by-Line Bloat Analysis

### Proposed Implementation (Task 2, lines 320-485):

| Lines | Purpose | Verdict |
|-------|---------|---------|
| 320-344 | Function signature, empty check | KEEP |
| 345-362 | Classify slices | KEEP |
| 364-382 | Build prefix section (all signatures) | KEEP |
| 384-390 | Append prefix_sections | DELETE (YAGNI) |
| 392-396 | Compute prefix metrics | KEEP |
| 397-401 | Comment about offset computation | DELETE (part of two-pass) |
| 402-421 | Build dynamic section | KEEP |
| 423-440 | **Two-pass assembly logic** | DELETE (use post-assembly .find()) |
| 441-465 | **Second assembly pass** | DELETE (part of two-pass) |
| 467-476 | Append dynamic + stats | KEEP |
| 477-483 | Cache stats footer | KEEP |
| 485 | Return | KEEP |

**LOC to delete:** 68 lines (prefix_sections + two-pass assembly)
**Remaining:** ~79 lines of actual formatting logic

---

## Recommended Simplified Implementation

```python
def _format_cache_friendly(pack: dict) -> str:
    """Format context pack for LLM provider prompt caching optimization.

    Layout:
    1. Header + cache hints JSON metadata
    2. All symbol signatures sorted by (file_path, symbol_id)
    3. CACHE_BREAKPOINT marker
    4. Changed symbol code bodies sorted by (file_path, symbol_id)
    5. Stats footer

    Args:
        pack: ContextPack dict with slices, unchanged list, cache_stats.

    Returns:
        Formatted string with cache-friendly structure.
    """
    slices = pack.get("slices", [])
    if not slices:
        return "# tldrs cache-friendly output\n\n# No symbols to display"

    # Classify slices (unchanged set used to identify changed symbols)
    unchanged_val = pack.get("unchanged", [])
    unchanged_set = set(unchanged_val) if isinstance(unchanged_val, list) else set()

    # Sort ALL slices deterministically by ID (already contains file:symbol)
    all_slices = sorted(slices, key=lambda s: s.get("id", ""))

    # Identify changed symbols with code bodies
    dynamic_body_slices = [
        s for s in all_slices
        if s.get("code") is not None and s.get("id", "") not in unchanged_set
    ]

    # Build prefix: ALL signatures
    prefix_parts = [f"## CACHE PREFIX ({len(all_slices)} symbols)", ""]
    for item in all_slices:
        symbol_id = item.get("id", "?")
        signature = item.get("signature", "")
        lines_range = item.get("lines") or []
        line_info = f" @{lines_range[0]}-{lines_range[1]}" if len(lines_range) == 2 else ""
        relevance = item.get("relevance", "")
        unchanged_marker = " [UNCHANGED]" if symbol_id in unchanged_set else ""
        prefix_parts.append(f"{symbol_id} {signature}{line_info} [{relevance}]{unchanged_marker}".strip())
    prefix_parts.append("")
    prefix_text = "\n".join(prefix_parts)

    # Compute prefix metrics
    prefix_token_est = _estimate_tokens(prefix_text)  # Use existing function
    import hashlib
    prefix_hash = hashlib.sha256(prefix_text.encode("utf-8")).hexdigest()[:16]

    # Build dynamic section: code bodies only
    dynamic_parts = []
    if dynamic_body_slices:
        dynamic_parts.append(f"## DYNAMIC CONTENT ({len(dynamic_body_slices)} changed symbols)")
        dynamic_parts.append("")
        for item in dynamic_body_slices:
            symbol_id = item.get("id", "?")
            signature = item.get("signature", "")
            dynamic_parts.append(f"### {symbol_id}")
            dynamic_parts.append(signature)
            code = item.get("code", "")
            dynamic_parts.append("```")
            dynamic_parts.extend(code.splitlines())
            dynamic_parts.append("```")
            dynamic_parts.append("")
    dynamic_text = "\n".join(dynamic_parts)
    dynamic_token_est = _estimate_tokens(dynamic_text)

    # Assemble output (single pass)
    hints_data = {
        "cache_hints": {
            "prefix_tokens": prefix_token_est,
            "prefix_hash": prefix_hash,
            "format_version": 1,
            # No breakpoint_char_offset — consumers can call .find("CACHE_BREAKPOINT")
        }
    }
    hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)

    header = "# tldrs cache-friendly output v1"
    breakpoint_line = f"<!-- CACHE_BREAKPOINT: ~{prefix_token_est} tokens -->"

    final_parts = [header, hints_line, "", prefix_text, breakpoint_line]
    if dynamic_parts:
        final_parts.append("")
        final_parts.extend(dynamic_parts)

    # Stats footer
    total_tokens = prefix_token_est + dynamic_token_est
    final_parts.append(
        f"## STATS: Prefix ~{prefix_token_est} tokens | Dynamic ~{dynamic_token_est} tokens | Total ~{total_tokens} tokens"
    )

    cache_stats = pack.get("cache_stats")
    if cache_stats:
        hit_rate = cache_stats.get("hit_rate", 0)
        hits = cache_stats.get("hits", 0)
        misses = cache_stats.get("misses", 0)
        final_parts.append(f"## Cache: {hits} unchanged, {misses} changed ({hit_rate:.0%} hit rate)")

    return "\n".join(final_parts)
```

**LOC:** ~79 lines (down from 147 in plan, down from 141 in existing code)
**Features:** All the useful ones (deterministic, prefix maximization, cache hints)
**Removed:** prefix_sections, two-pass assembly, nested token function, unnecessary comments
