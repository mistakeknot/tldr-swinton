# PDG-Guided Minimal Slicing

**Date:** 2026-01-17
**Status:** Draft
**Priority:** #3 (per Oracle evaluation)
**Expected Impact:** 30-50% additional savings on function bodies

## Overview

Add a `--compress pdg` mode for DiffLens that uses Program Dependence Graph analysis to include only code statements relevant to diff hunks. Key insight from Oracle: slices should be **exact code** (not summaries) to remain edit-safe for agents.

### Current State

1. **PDG Extractor** (`pdg_extractor.py`):
   - Already implements `backward_slice(line, variable)` and `forward_slice(line, variable)`
   - Combines CFG (control dependencies) and DFG (data dependencies)
   - Returns `set[int]` of line numbers
   - Multi-language support via tree-sitter

2. **DiffLens Engine** (`engines/difflens.py`):
   - `build_diff_context_from_hunks()` extracts windowed code around diff lines
   - Uses `_extract_windowed_code()` and `_two_stage_prune()` for compression
   - Tracks `diff_lines` per symbol in metadata

3. **Slice Engine** (`engines/slice.py`):
   - Wrapper: `get_slice(source, function_name, line, direction, variable, language)`
   - Returns line numbers only - needs enhancement for code extraction

### Gap Analysis

| Capability | Status | Work Needed |
|-----------|--------|-------------|
| PDG extraction | Done | None |
| Backward/forward slicing | Done | None |
| Diff line to slice mapping | Partial | Connect diff_lines to PDG slice |
| Code extraction from slice | Missing | Extract exact lines from slice set |
| DiffLens integration | Missing | New `--compress pdg` mode |

## Architecture Design

### Data Flow

```
DiffLens Engine
    |
    v
[hunks] -> map_hunks_to_symbols() -> {symbol_id: {diff_lines}}
    |
    v (when --compress=pdg)
PDG Slicer
    |
    v
For each symbol with diff_lines:
  1. Extract PDG for the function
  2. For each diff_line: compute backward_slice(diff_line)
  3. Union all slice line sets
  4. Extract exact source lines for union
    |
    v
ContextPack with sliced code (exact lines)
```

### Key Design Decisions

1. **Backward slice only (initial)**: Focus on "what code affects this diff line"
2. **Exact code extraction**: Preserve original indentation and formatting
3. **Slice union**: Multiple diff lines in a function → union their backward slices
4. **Graceful degradation**: If PDG fails, fall back to windowed extraction
5. **Line continuity markers**: Insert `...` between non-contiguous ranges

## Implementation Tasks

### Task 1: Add PDG slice code extraction utility

**Files:**
- Modify: `src/tldr_swinton/engines/slice.py`
- Test: `tests/test_slice_code.py`

```python
def get_slice_code(
    source_or_path: str,
    function_name: str,
    line: int,
    direction: str = "backward",
    variable: str | None = None,
    language: str = "python",
) -> tuple[str, list[int]]:
    """Get sliced code as exact source lines.

    Returns:
        (code_string, sorted_line_numbers)
    """
```

### Task 2: Add multi-line slice union utility

**Files:**
- Modify: `src/tldr_swinton/engines/slice.py`

```python
def get_slice_code_for_diff_lines(
    source_or_path: str,
    function_name: str,
    diff_lines: list[int],
    language: str = "python",
    include_forward: bool = False,
) -> tuple[str, list[int]]:
    """Get sliced code for multiple diff lines (union of backward slices)."""
```

### Task 3: Integrate PDG slicing into DiffLens

**Files:**
- Modify: `src/tldr_swinton/engines/difflens.py`
- Test: `tests/test_difflens_pdg_slice.py`

```python
def _extract_pdg_sliced_code(
    source: str,
    function_name: str,
    diff_lines: list[int],
    symbol_start: int,
    symbol_end: int,
    language: str,
) -> tuple[str | None, list[int]]:
    """Extract PDG-sliced code for a function with diff lines."""
```

In `build_diff_context_from_hunks()`, add branch for `compress="pdg"`:
- Extract function name from symbol_id
- Call `_extract_pdg_sliced_code()`
- Fall back to windowed if PDG fails
- Add `slice_mode: "pdg" | "windowed_fallback"` to metadata

### Task 4: Add CLI compress choice

**Files:**
- Modify: `src/tldr_swinton/cli.py`

```python
diff_p.add_argument(
    "--compress",
    choices=["none", "two-stage", "chunk-summary", "pdg"],
    default="none",
    help="Compression mode (default: none)",
)
```

### Task 5: Add evaluation metrics

**Files:**
- Modify: `evals/difflens_eval.py`

```python
def _run_pdg_slice_eval(repo: Path, language: str, label: str) -> list[EvalResult]:
    """Evaluate PDG slicing vs baseline windowed extraction."""
```

Metrics:
- Savings vs baseline (target: >=10%)
- PDG extraction success rate
- Latency (allow up to 3x slower than baseline)

### Task 6: Add workflow regression test

**Files:**
- Modify: `evals/agent_workflow_eval.py`

Ensure PDG-sliced code is edit-safe (exact source, not summarized).

### Task 7: Documentation

**Files:**
- Modify: `docs/agent-workflow.md`
- Modify: `README.md`

```markdown
### PDG Slicing (Experimental)

For maximum token savings, use `--compress pdg`:

```bash
tldrs diff-context --compress pdg --budget 2000
```

Uses Program Dependence Graph analysis to include only statements
affecting the diff. Output is exact code (edit-safe).
```

## Promotion Gate Criteria

Per AGENTS.md, experimental compression modes must pass:

1. **>=10% additional savings** vs diff+deps baseline in `evals/difflens_eval.py`
2. **No regressions** on `evals/agent_workflow_eval.py`
3. **At least one manual spot check** on a real repo

## Eval Criteria and Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Token savings vs baseline | >=10% | `evals/difflens_eval.py` |
| PDG extraction success | >80% | Count pdg vs fallback slices |
| Latency overhead | <3x baseline | Time comparison |
| Edit safety | 100% exact code | No summarization in output |
| No regressions | Pass all evals | `evals/agent_workflow_eval.py` |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| PDG extraction fails | Missing context | Graceful fallback to windowed |
| Latency increase | Slower responses | Cache PDG per function |
| Over-slicing (too little) | Broken context | Include diff lines + control structure |
| Under-slicing (too much) | Minimal savings | Tune backward slice depth |

## Testing Matrix

| Language | PDG Extraction | Slice Code | DiffLens Integration |
|----------|---------------|------------|---------------------|
| Python | Supported | Test | Test |
| TypeScript | Supported | Test | Test |
| Rust | Supported | Test | Test |
| Go | Supported | Test | Test |
| Other | Fallback | N/A | Windowed |

## Critical Files

| File | Purpose |
|------|---------|
| `src/tldr_swinton/engines/slice.py` | Add `get_slice_code_for_diff_lines()` |
| `src/tldr_swinton/engines/difflens.py` | Integrate PDG slicing |
| `src/tldr_swinton/pdg_extractor.py` | Existing PDG infrastructure |
| `evals/difflens_eval.py` | Add PDG slice metrics |
| `src/tldr_swinton/cli.py` | Add `pdg` to `--compress` |
