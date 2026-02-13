---
title: Extract engine-internal logic into shared modules before adding new modes
category: best-practices
severity: medium
tags: [refactoring, architecture, block-compression, knapsack, difflens]
date: 2026-02-12
symptoms:
  - Plan proposes implementing an algorithm that already exists inside an engine
  - New compression/processing mode duplicates existing logic in a different module
  - Architecture review finds "collision risk" between proposed and existing code
root_cause: >
  Engine modules (e.g., difflens.py) accumulate private helper functions that
  implement general-purpose algorithms (block segmentation, knapsack DP, scoring).
  When a new mode needs the same algorithm, the temptation is to write it fresh
  in a new module — creating duplicate, divergent implementations.
solution: >
  Extract the existing battle-tested logic into a shared module first, then add
  the new mode as a thin wrapper. The existing engine becomes a thin caller of
  the shared module, preserving backwards compatibility.
---

## Problem

When adding `--compress blocks` (AST-based block compression), the initial plan proposed writing a new `block_compress.py` from scratch. Architecture review revealed that `difflens.py` already contained a 140-line `_two_stage_prune()` function implementing the exact same algorithm: indent-based block segmentation + 0/1 knapsack DP + diff-aware scoring.

Building a new module would have created two divergent knapsack implementations that would inevitably drift.

## Solution Pattern: Extract → Upgrade → Wire

### Step 1: Extract existing logic into shared module

Move private helpers from the engine to a new public module:

```
_split_blocks_by_indent()  →  block_compress.segment_by_indent()
_two_stage_prune() knapsack →  block_compress.knapsack_select()
scoring logic              →  block_compress.score_blocks()
```

Keep the **same return signature** so the engine's callers don't change:

```python
# block_compress.py — same (str, int, int) return as _two_stage_prune()
def compress_function_body(...) -> tuple[str, int, int]:
```

### Step 2: Add the new capability

With the shared module in place, add the upgrade (AST-based segmentation) alongside the extracted logic:

```python
def segment_into_blocks(source, language):
    """AST-based → indent-based fallback chain."""
    ast_blocks = segment_by_ast(source, language)
    if ast_blocks:
        return ast_blocks
    return segment_by_indent(source.splitlines())
```

### Step 3: Wire the new mode at the same integration point

```python
# difflens.py — same wiring point, new branch
if compress == "blocks":
    from ..block_compress import compress_function_body
    code, block_count, dropped = compress_function_body(code, ...)
elif compress == "two-stage":
    code, block_count, dropped = _two_stage_prune(code, ...)  # legacy
```

## Key Insight: Fallback Chains for Graceful Degradation

The AST-based approach requires tree-sitter support for the target language. Not all languages have it. The fallback chain ensures the feature never breaks:

```
AST-based (tree-sitter) → indent-based (heuristic) → no-op (return full code)
```

This pattern applies anywhere you add a capability that depends on optional infrastructure.

## Checklist for Future Extractions

1. **Find the existing implementation** — search for the algorithm name or pattern in engine code
2. **Verify return signature compatibility** — the shared module must match the engine's caller contract
3. **Preserve the old mode** — don't break `--compress two-stage` when adding `--compress blocks`
4. **Add fallback for optional deps** — tree-sitter, embeddings, etc. may not be available
5. **Run architecture review before implementation** — catches duplication early

## Related

- `docs/research/review-block-compression-plan.md` — architecture review that caught the duplication
- `docs/plans/2026-02-12-longcodezip-block-compression.md` — revised plan after review
- `src/tldr_swinton/modules/core/block_compress.py` — the extracted shared module
