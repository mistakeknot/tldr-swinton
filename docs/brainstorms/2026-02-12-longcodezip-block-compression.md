# Brainstorm: LongCodeZip Block-Level Compression

**Date**: 2026-02-12
**Bead**: bdi — Research and prototype LongCodeZip block-level compression
**Status**: Brainstorm complete

## Problem Statement

tldr-swinton's zoom levels have a gap between L2 (body skeleton — control flow structure only) and L3/L4 (windowed/full code). When a function body is large but only parts are relevant to the current task, there's no intermediate option that preserves semantically important blocks while eliding boilerplate.

Current `--budget` handling truncates or omits entire functions. We need **within-function** compression that keeps the most relevant blocks and elides the rest.

## Research Summary

LongCodeZip (ASE 2025, arXiv 2510.00446) achieves 5.6x compression with no quality loss via:
1. **Stage 1**: tree-sitter function chunking + AMI-based ranking
2. **Stage 2**: Perplexity-based block boundary detection + 0/1 knapsack DP

Full details in `docs/research/research-longcodezip-paper.md`.

## Proposed Approach: Heuristic Block Compression (No LM Dependency)

Extract the paper's core insight (block segmentation + knapsack) but replace LM perplexity with existing tldrs signals:

### Block Segmentation (from tree-sitter AST)
- Control flow boundaries (if/for/while/try/match)
- Blank-line separated blocks
- Decorator + function/class definition starts
- Assignment/expression statement groups

### Block Scoring (from existing infrastructure)
- **Semantic similarity** to query (embedding infrastructure already exists)
- **Diff proximity** (blocks touching changed lines score higher)
- **Call graph relevance** (blocks containing calls to/from focal functions)
- **Structural importance** (return statements, error handling, assignments to key variables)

### Budget Allocation
- 0/1 knapsack DP per function body
- Elided blocks → `# ... (N lines, M tokens)` marker
- Preserves source order of selected blocks

## Integration Points

1. **New zoom level L2.5** or flag `--compress blocks`
2. **Post-processor** in ContextPack pipeline (after zoom, before format)
3. **Budget-aware** — only activates when budget < total tokens (no-op otherwise)

## Risk Assessment

- **Low risk**: Pure Python, no new deps, uses existing tree-sitter
- **Medium confidence**: Block boundaries from AST are less precise than LM perplexity, but free
- **Validation path**: Compare compressed output quality against L2 and L4 on interbench evals

## Open Questions

1. Should this be a new ZoomLevel enum value or a separate compression flag?
2. How to handle cross-block dependencies (e.g., variable defined in block A, used in block B)?
3. Elision marker format — minimal (`# ...`) vs informative (`# ... (error handling, 12 lines)`)?
