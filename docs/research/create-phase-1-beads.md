# Phase 1 (Quick Wins) — Beads Issues Created

**Date:** 2026-02-12
**Context:** Token efficiency review, Phase 1 quick wins

## Issues Created

| ID | Type | Priority | Title | Est. Savings |
|----|------|----------|-------|-------------|
| `tldr-swinton-7kb` | task | P1 | Change MCP context() defaults to ultracompact + budget=4000 | 30-50% per context() call |
| `tldr-swinton-q5e` | bug | P1 | Remove diff-context from setup.sh to fix double-fire with session-start skill | ~1,000-2,000 tokens/session |
| `tldr-swinton-3ia` | feature | P1 | Create compact extract format for PostToolUse:Read hook | ~25,000 tokens/session |
| `tldr-swinton-563` | task | P2 | Delete suggest-recon.sh and update AGENTS.md stale references | correctness/routing |

## Summary

4 beads issues created for Phase 1 of the token efficiency review:

1. **MCP context() defaults** (`tldr-swinton-7kb`): The MCP `context()` tool currently defaults to `format='text'` and `budget=None`, producing verbose output. The plugin slash commands already hardcode better defaults (`ultracompact`, `budget=4000`), but direct MCP tool calls — which are the primary interface for Claude Code — get the verbose path. Changing defaults in `mcp_server.py:208-209` yields 30-50% savings per call with zero behavior change for plugin users.

2. **Setup.sh double-fire bug** (`tldr-swinton-q5e`): Both `setup.sh` (lines 53-59) and the `tldrs-session-start` skill run `tldrs diff-context --preset compact`, producing identical output that gets emitted twice per session. Fix: strip diff-context/structure execution from the setup hook, keeping only install checks, ast-grep check, background prebuild, and project stats.

3. **Compact extract format** (`tldr-swinton-3ia`): The PostToolUse:Read hook runs full `tldrs extract` (~6,400 tokens) for every code file >300 lines. Most of the output (call_graph, redundant params arrays, `is_async:false`, empty decorators) is never used by Claude Code. A compact mode returning only function signatures with line numbers, class names with method signatures, and import summary would target ~800 tokens per file — an 87% reduction, saving ~25,000 tokens per session assuming 5 large-file reads.

4. **Dead code cleanup** (`tldr-swinton-563`): Delete `suggest-recon.sh` (dead code, not registered in hooks.json) and fix 3 stale references in AGENTS.md that still list retired skills (`tldrs-find-code`, `tldrs-understand-symbol`, `tldrs-explore-file`). Not a token savings issue per se, but stale docs cause Claude Code to attempt non-existent skills, wasting routing tokens.

## Execution Order Recommendation

1. `tldr-swinton-q5e` (bug fix, simplest — just delete lines from setup.sh)
2. `tldr-swinton-7kb` (2-line default change in mcp_server.py)
3. `tldr-swinton-563` (cleanup, no code logic changes)
4. `tldr-swinton-3ia` (feature work, needs new format + tests)

## Combined Impact

Conservative estimate: **~28,000-32,000 tokens saved per session** from items 1-3 alone. Item 4 improves routing accuracy, reducing wasted tool calls.
