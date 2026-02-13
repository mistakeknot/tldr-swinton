# Phase 2 — API Surface Expansion: Beads Issues Created

**Date:** 2026-02-12
**Phase:** Token Efficiency Review, Phase 2 (API Surface Expansion)

## Summary

Created 4 beads issues (3 features, 1 bug) to expose existing compression capabilities through the MCP API surface, making them accessible to Claude Code and other MCP clients.

## Issues Created

| Bead ID | Title | Type | Priority |
|---------|-------|------|----------|
| `tldr-swinton-b5l` | Add preset parameter to MCP context() tool | feature | P2 |
| `tldr-swinton-6ex` | Add max_lines and max_bytes to MCP diff_context() tool | feature | P2 |
| `tldr-swinton-5lm` | Add strip_comments to build_context_pack_delta() | bug | P2 |
| `tldr-swinton-bnv` | Create 'agent' preset tuned for Claude Code | feature | P2 |

## Issue Details

### 1. `tldr-swinton-b5l` — Add preset parameter to MCP context() tool

**Rationale:** The `context()` MCP tool is the primary entry point for Claude Code to retrieve symbol-level context, but it lacks preset support. The `diff_context()` tool already has it. This is the highest-leverage single change because it exposes all compression options (compact, minimal, multi-turn) via a single parameter.

**Implementation notes:**
- Add `preset: str | None` parameter to context() tool definition
- Map to same preset system used by diff_context() and CLI
- Consider converting context() from daemon-proxied to direct-call (like diff_context) to allow passing all parameters directly
- Files: `mcp_server.py:202-253`, related `cli.py:1166-1219`

### 2. `tldr-swinton-6ex` — Add max_lines and max_bytes to MCP diff_context() tool

**Rationale:** The CLI has `--max-lines` and `--max-bytes` flags for output capping, but the MCP diff_context() tool does not expose them. Without these, MCP clients cannot control output size, leading to potential context window waste.

**Implementation notes:**
- Add `max_lines: int | None` and `max_bytes: int | None` as optional parameters
- Apply truncation via `output_formats.truncate_output()` before returning
- File: `mcp_server.py:562-644`

### 3. `tldr-swinton-5lm` — Add strip_comments to build_context_pack_delta() (BUG)

**Rationale:** This is a silent correctness bug. `build_context_pack()` (non-delta path, lines 86-185) applies `strip_comments`, but `build_context_pack_delta()` (lines 187-329) lacks the parameter entirely. When delta mode is active (the common path for diff-based workflows), comment stripping is silently broken — meaning users requesting comment stripping get no effect.

**Implementation notes:**
- Add `strip_comments: bool = False` parameter to `build_context_pack_delta()`
- Apply identically to the non-delta path's implementation
- File: `contextpack_engine.py:187-329`

### 4. `tldr-swinton-bnv` — Create 'agent' preset tuned for Claude Code

**Rationale:** No existing preset is tuned for Claude Code's 200K context window. The current `compact` preset uses `budget=2000` which is too restrictive for meaningful multi-file context. An `agent` preset would provide maximum compression with a generous budget.

**Implementation notes:**
- New preset name: `agent`
- Settings: ultracompact format, budget=4000, compress_imports=True, strip_comments=True, type_prune=True
- File: `presets.py:12-33`

## Dependency Graph

```
tldr-swinton-bnv (agent preset)
    └── tldr-swinton-b5l (context() preset param) — needs preset to exist
    
tldr-swinton-5lm (strip_comments bug) — independent, should fix first
tldr-swinton-6ex (max_lines/max_bytes) — independent
```

**Recommended execution order:**
1. `tldr-swinton-5lm` (bug fix, independent, correctness issue)
2. `tldr-swinton-bnv` (create agent preset, needed by context() tool)
3. `tldr-swinton-b5l` (add preset to context(), highest leverage)
4. `tldr-swinton-6ex` (add output capping to diff_context())

## Impact Assessment

These four changes together would make the full compression pipeline accessible through MCP:
- **Before:** Claude Code can only use default (verbose) output from context() and uncapped diff_context()
- **After:** Claude Code can request agent-optimized output with comment stripping, import compression, type pruning, and output size limits

Estimated token savings when all four are implemented: 40-60% reduction in context tokens for typical multi-file queries, based on Phase 1 measurements of individual compression features.
