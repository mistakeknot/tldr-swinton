# Plan: Block-Level Compression (LongCodeZip-Inspired)

**Bead**: bdi — Research and prototype LongCodeZip block-level compression
**Date**: 2026-02-12
**Research**: `docs/research/research-longcodezip-paper.md`
**Brainstorm**: `docs/brainstorms/2026-02-12-longcodezip-block-compression.md`
**Architecture Review**: `docs/research/review-block-compression-plan.md`

## Goal

Extract the existing block compression logic from `difflens.py` (`_two_stage_prune`
+ `_split_blocks_by_indent`) into a standalone `block_compress.py` module, upgrade
block detection from indent-based to AST-based (tree-sitter), and expose as
`--compress blocks` alongside existing `two-stage` and `chunk-summary` modes.

## Design Decisions (from architecture review)

1. **Refactor, don't duplicate**: Extract battle-tested `_two_stage_prune()` into
   shared `block_compress.py`. DiffLens becomes a thin wrapper calling the shared module.

2. **Wiring point**: DiffLens engine, not output_formats. Compression already happens
   in DiffLens (`compress` param flows from CLI → engine → `_two_stage_prune()`). The
   new `blocks` mode follows the same path.

3. **Budget model unchanged**: Keep the existing binary budget model in ContextPackEngine
   (full code / signature-only / drop). Block compression applies *within* the "full code"
   tier — it doesn't change when a symbol gets included, just how much of its body appears.

4. **Nested blocks**: Extract only top-level-within-function AST nodes. A `for` inside an
   `if` is part of the `if` block, not a separate block. This matches the existing
   `_split_blocks_by_indent()` behavior.

5. **Fallback chain**: AST-based (tree-sitter) → indent-based (existing) → no-op (full code).

6. **Import compression runs first**: `compress_imports` is a whole-file transform; block
   compression is per-symbol. Order: imports first, then blocks.

7. **`chunk-summary` unchanged**: It's fundamentally different (replaces code with text summary).
   `blocks` is parallel to `two-stage`, not a replacement for `chunk-summary`.

8. **Incremental diffs excluded**: Block compression does not apply to `cache-friendly`
   incremental representation. It applies to full function bodies in ultracompact format.

## Implementation Steps

### Step 1: Extract block compression module
**File**: `src/tldr_swinton/modules/core/block_compress.py` (new)

Extract from `difflens.py`:
- `_split_blocks_by_indent()` → `segment_by_indent()` (public, renamed)
- `_two_stage_prune()` knapsack logic → `knapsack_select()` (public, extracted)

Add new:
- `segment_by_ast()` — tree-sitter block detection (top-level-within-function nodes)
- `segment_into_blocks()` — dispatcher: tries AST, falls back to indent
- `compress_function_body()` — main entry point, returns `(compressed_code, metadata_dict)`

**CodeBlock dataclass**:
```python
@dataclass
class CodeBlock:
    start_line: int   # 0-based within the source
    end_line: int     # 0-based, inclusive
    text: str
    token_count: int  # chars // 4 estimate
    relevance: float  # 0.0-1.0
```

**Scoring** (mirrors existing DiffLens scoring):
- +10.0 per diff line overlap
- +3.0 for adjacency to diff blocks
- +0.5 per control-flow keyword (return, raise, yield, if, for, etc.)
- Blocks with diff overlap are `must_keep` (never dropped)

**Elision marker**: `# ... (N lines elided)` — more informative than DiffLens's bare `...`

### Step 2: Refactor DiffLens to use shared module
**File**: `src/tldr_swinton/modules/core/engines/difflens.py` (modify)

- `_two_stage_prune()` becomes a thin wrapper calling `compress_function_body()`
- `_split_blocks_by_indent()` removed (moved to block_compress.py)
- `compress == "blocks"` added as a new branch (same wiring point as `two-stage`)
- `compress == "two-stage"` unchanged behavior (uses same shared code)

### Step 3: CLI flag + preset
**File**: `src/tldr_swinton/cli.py` (modify)

- Add `"blocks"` to `--compress` choices
- Do NOT change presets yet (let it stabilize first, upgrade presets in a follow-up)

### Step 4: Tests
**File**: `tests/test_block_compress.py` (new)

- `test_segment_by_indent()` — existing behavior preserved
- `test_segment_by_ast_python()` — AST-based on a sample Python function
- `test_segment_fallback()` — AST fails → indent fallback → no-op
- `test_knapsack_optimal()` — known-optimal solution for small input
- `test_compress_noop_when_fits()` — body fits budget → unchanged
- `test_compress_elision_marker()` — dropped blocks get markers
- `test_compress_must_keep_diff_blocks()` — diff blocks never dropped

## Out of Scope

- LM-based perplexity scoring (Phase 2)
- Cross-block dependency tracking
- ContextPackEngine budget allocation changes
- Preset updates (follow-up after eval validation)
- `context` command integration (diff-context only for now)
- Pluggable scorer interface (add when needed for Phase 2)

## Success Criteria

- `--compress blocks` produces equivalent or better output than `--compress two-stage`
- DiffLens `_two_stage_prune()` refactored with no behavior change (regression-free)
- Fallback chain works (AST → indent → no-op)
- Tests pass
