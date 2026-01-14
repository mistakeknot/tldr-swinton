# Oracle Review Implementation Plan (Re-sequenced)

**Created:** 2026-01-14
**Updated:** 2026-01-14
**Status:** Ready for implementation
**Estimated Total Effort:** 4-7 days across 3–4 PRs

## Status Update (as of 2026-01-14)

**Already completed in `main`:**
- **Python method name collisions (Oracle #11)**: call graph now uses qualified method names (`Class.method`) to prevent clobbering. This fixes the "methods with same name overwrite each other" issue in Python call extraction.
- **Real token budgeting** now uses tiktoken-backed estimation (not an Oracle item, but removes a correctness gap for budgets).

**Still open (Oracle items):**
- Header omission bug in budgeted ultracompact output (Oracle #1)
- Unbounded call list expansion in ultracompact (Oracle #2)
- DiffLens signatures_only duplication (Oracle #3)
- Entry-point ambiguity explosion (Oracle #4)
- DiffLens windowed slicing (Oracle #5)
- JSON compact output defaults (Oracle #6/#12)
- diff_lines range encoding (Oracle #7)
- Per-line indentation in diff pack (Oracle #8)
- TS this.method() class qualification (Oracle #10)

---

## Re-sequenced Implementation Order

### PR1: Output Correctness + Explosion Control (P0, 1-2 days)

**Goal:** Eliminate hard correctness bugs and output blow-ups.

#### Task 1.1: Fix Budgeted Ultracompact Header Omission Bug (CRITICAL)

**Problem:** When header doesn't fit budget, output emits `P0:Symbol` references without defining `P0`.

**File:** `src/tldr_swinton/output_formats.py`

**Fix:** If header doesn't fit, re-render all symbols using inline `file:symbol` format (no path IDs). Only emit path dictionary when actually used.

**Patch Sketch:**
```python
def _format_symbol_inline(name: str, file_path: str) -> str:
    file_part, sym = _split_symbol(name, file_path)
    return f"{file_part}:{sym}"

# If header doesn't fit: re-render collected using inline format.
```

**Tests:**
- Budget fits header + content → header emitted
- Budget fits content but not header → inline format only
- Budget fits neither → graceful truncation

---

#### Task 1.2: Cap and Dedupe Call Lists (CRITICAL)

**Problem:** Ultracompact prints ALL callees; call-heavy functions explode output.

**File:** `src/tldr_swinton/output_formats.py`

**Fix:**
1. `MAX_CALLS = 12`
2. `_dedupe_preserve()` helper
3. Truncate with `(+N)` suffix
4. Apply to `_format_ultracompact()` and `_format_ultracompact_budgeted()`

**Token Savings:** 20-80% on call-heavy contexts.

---

#### Task 1.3: Entry-Point Ambiguity Control (CRITICAL)

**Problem:** `resolve_entry_symbols()` returns all matches for common names → BFS explosion.

**File:** `src/tldr_swinton/api.py`

**Fix:** Return only best match when multiple candidates found.

**Patch Sketch:**
```python
if len(matches) > 1:
    sorted_matches = sorted(matches, key=score_match)
    logger.warning(...)
    return [sorted_matches[0]]
```

**Token Savings:** Prevents 10x-100x blowups.

---

#### Task 1.4: TS this.method() Class Qualification (HIGH)

**Problem:** TS `this.method()` is currently recorded as plain `method`, not `Class.method`.

**File:** `src/tldr_swinton/cross_file_calls.py`

**Fix:** Track class context for TS method definitions and map `this.method()` to `Class.method` when possible.

**Note:** This is a correctness fix but less urgent than 1.1-1.3.

---

### PR1 Testing Checklist

- [ ] `tldrs context main --budget 100 --format ultracompact` never emits undefined `P#` refs
- [ ] `tldrs context main --format ultracompact` caps calls at 12 with `(+N)`
- [ ] Ambiguous entry points return a single best match with warning
- [ ] Run tests: `pytest tests/`

---

### PR2: DiffLens Payload Pruning + True Slice Efficiency (P1, 1-2 days)

**Goal:** Shrink DiffLens outputs without losing relevance.

#### Task 2.1: Remove `signatures_only` Duplication (CRITICAL)

**Problem:** Pack includes both `slices[].code = null` AND `signatures_only` list (redundant).

**Files:**
- `src/tldr_swinton/api.py`
- `src/tldr_swinton/output_formats.py`

**Fix:** Remove `signatures_only` entirely; infer from `slice.code == null`.

**Note:** Breaking change to JSON schema — call out in changelog.

---

#### Task 2.2: Range-Encode `diff_lines` (HIGH)

**Problem:** Large hunks store hundreds of line numbers.

**File:** `src/tldr_swinton/api.py`

**Fix:** Convert sorted line list to ranges: `[1,2,3,5,6] -> [[1,3],[5,6]]`.

**Token Savings:** 10x-100x for large hunks.

---

#### Task 2.3: Window Code Around Diff Lines (HIGH)

**Problem:** DiffLens extracts entire symbol body even if only a few lines changed.

**File:** `src/tldr_swinton/api.py`

**Fix:** Extract windowed code around diff lines (default ±6 lines) with `...` separators.

**Token Savings:** 60-95% of changed-symbol code tokens.

---

#### Task 2.4: Remove Per-Line Indentation in Diff Pack (HIGH)

**Problem:** Per-line indentation adds ~0.5 tokens/line.

**File:** `src/tldr_swinton/output_formats.py`

**Fix:** Use fenced code blocks instead of prefixing every line.

---

### PR2 Testing Checklist

- [ ] `tldrs diff-context --format json` has no `signatures_only`
- [ ] `diff_lines` encoded as ranges
- [ ] Windowed code shows `...` between non-adjacent blocks
- [ ] Run tests: `pytest tests/`

---

### PR3: Output Compactness + Bench Metrics (P2, 1-2 days)

**Goal:** Reduce payload size further and add measurement.

#### Task 3.1: Compact JSON Output by Default (HIGH)

**File:** `src/tldr_swinton/output_formats.py`

**Fix:**
- `--format json` → compact (no indent)
- add `--format json-pretty` for debugging

---

#### Task 3.2: Add Benchmark Metrics (MEDIUM)

**File:** `tldr-bench/tldr_bench/metrics.py`

**Add metrics:** tokens, compression ratio, budget compliance, avg code tokens per symbol, window size utilization.

---

### PR3 Testing Checklist

- [ ] `--format json` is compact; `--format json-pretty` is readable
- [ ] Metrics show improved compression + budget compliance
- [ ] Run tests: `pytest tests/`

---

## Updated Success Metrics

| Metric | Target |
|--------|--------|
| Call-heavy context token reduction | 20-80% |
| DiffLens code token reduction | 60-95% |
| JSON payload reduction | 25-45% |
| Budget compliance | >95% |
| Zero undefined P# refs | ✓ |
| Zero entry-point explosions | ✓ |

---

## Appendix: Oracle Review Raw Findings (for reference)

### CRITICAL
1. Ultracompact budgeted output can emit P#: references without header mapping
2. Unbounded call list expansion in ultracompact output
3. Duplicate "signatures_only" representation in DiffLens packs
4. Entry-point ambiguity can explode context size

### HIGH
5. DiffLens emits entire symbol body instead of slicing around diff lines
6. JSON output uses indent=2
7. diff_lines stored as full list instead of ranges
8. Per-line "  " prefix in code output

### MEDIUM
9. Adjacency lists can contain duplicates and are unordered
10. TS "this.method()" call not class-qualified
11. Python call extraction overwrites methods with same name

### LOW
12. CLI commands pretty-print JSON by default
