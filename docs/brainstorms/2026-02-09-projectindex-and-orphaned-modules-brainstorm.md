# Brainstorm: ProjectIndex Extraction + Orphaned Module Wiring

**Date**: 2026-02-09
**Beads**: tldr-swinton-bac, tldr-swinton-48i
**Status**: Ready for planning

## What We're Building

### Bead bac: Shared ProjectIndex

Extract the duplicated symbol scanning logic (found in symbolkite.py, difflens.py, and cli.py) into a single `ProjectIndex` class. Every project-scoped engine currently re-scans all files from scratch on every call — building symbol_index, name_index, file_name_index, call_graph, and adjacency dicts independently.

The ProjectIndex will be constructed once and passed to engines, eliminating ~500 lines of duplication and making the index reusable across engine calls within a session.

### Bead 48i: Wire Orphaned Modules

Four complete modules (~2000 lines total) have zero or minimal callers:

| Module | What it does | Integration point |
|--------|-------------|-------------------|
| attention_pruning.py | Learn from agent edit patterns, rerank candidates by historical signal | ContextPackEngine post-processing |
| edit_locality.py | Extract edit boundaries, invariants, patch templates | ContextPackEngine candidate enrichment |
| coherence_verify.py | Cross-file edit validation (signature mismatches, type conflicts) | Optional validator after ContextPack |
| context_delegation.py | Decompose large contexts into sub-tasks for parallel agents | Already has 1 caller (mcp_server.py), extend |

## Why This Approach

### Pure refactoring for ProjectIndex (no SalsaDB)

- SalsaDB and IncrementalParser exist and are ready, but adding caching simultaneously increases blast radius
- Pure extraction is testable: engines should produce identical output before and after
- Caching can be layered on afterward as a separate bead with the ProjectIndex as its foundation
- YAGNI: the immediate win is deduplication, not performance

### Wire all 4 orphaned modules

- All four have complete implementations with tests/databases
- attention_pruning and edit_locality directly improve ContextPack quality
- coherence_verify serves as an optional safety net (can be off by default)
- context_delegation is already partially wired; extending it is low risk

## Key Decisions

1. **ProjectIndex is a plain class, not cached** — No SalsaDB integration in this iteration
2. **Wire all 4 modules** — None are dead code; all serve a purpose
3. **ContextPackEngine gets post-processing hooks** — New phase between candidate sorting and token estimation
4. **coherence_verify is opt-in** — Enabled via flag, not default pipeline
5. **Dependency order preserved** — bac ships first, 48i builds on it

## Duplication Map (from research)

Identical pattern repeated 3+ times:
```
1. iter_workspace_files(project, extensions)
2. extractor.extract(file_path) per file
3. register_symbol() into symbol_index, name_index, file_name_index
4. build_project_call_graph(str(project))
5. Build adjacency dict from call_graph.edges
```

Found in:
- symbolkite.py:216-298 and 661-738
- difflens.py:576-663
- cli.py: various CLI commands

## Open Questions

- None — scope is well-defined. Implementation details belong in the plan.

## Future Work (Not This Iteration)

- Wire SalsaDB around ProjectIndex for incremental updates
- Integrate IncrementalParser into HybridExtractor for file-change detection
- Add ContextPackEngine support for pluggable reranking strategies
