# Bead 563: Cleanup Stale References

## Summary

Deleted dead code (`suggest-recon.sh`) and updated `AGENTS.md` to reflect the current plugin hook/skill configuration.

## Changes Made

### 1. Deleted `.claude-plugin/hooks/suggest-recon.sh`

This file was a `PreToolUse` hook for Read/Grep that nudged agents to run `tldrs diff-context` before reading code files. It was **not registered in `hooks.json`** and therefore never executed. It was already noted as "(legacy, not registered)" in `CLAUDE.md`.

**Why it existed:** Originally wired as a PreToolUse hook on Read and Grep (v0.6.2), it was later removed from `hooks.json` when the plugin was restructured (v0.5+), but the file itself was never deleted.

### 2. Updated AGENTS.md: Removed 3 Retired Skills

Removed from the autonomous skills table:
- `tldrs-find-code` (replaced by MCP `tldr-code` tools: `find`, `semantic`)
- `tldrs-understand-symbol` (replaced by MCP `tldr-code` tools: `context`, `impact`)
- `tldrs-explore-file` (replaced by MCP `tldr-code` tools: `cfg`, `dfg`, `extract`)

These skills were retired in a previous commit (ae23075: "refactor: retire 3 skills replaced by MCP tools, keep orchestration-only") but the AGENTS.md table was not updated at that time.

Remaining skills (3 orchestration-only):
- `tldrs-session-start` — session initialization
- `tldrs-map-codebase` — architecture exploration
- `tldrs-ashpool-sync` — eval coverage sync

### 3. Updated AGENTS.md: Fixed Hooks Description

**Before (stale):**
```
- PreToolUse on Read and Grep: Suggests running tldrs recon before reading files
- SessionStart (setup.sh): ...runs prebuild in background
```

**After (matches hooks.json):**
```
- PreToolUse on Serena replace_symbol_body and rename_symbol: Runs tldrs impact to show callers before edits
- PostToolUse on Read: Runs compact tldrs extract on large code files (>300 lines, once per file per session)
- SessionStart (setup.sh): ...provides project summary
```

This now accurately reflects what `hooks.json` actually registers:
- `PreToolUse` matchers: `mcp__plugin_serena_serena__replace_symbol_body`, `mcp__plugin_serena_serena__rename_symbol` (runs `pre-serena-edit.sh`)
- `PostToolUse` matcher: `Read` (runs `post-read-extract.sh`)
- `Setup` (runs `setup.sh`)

### 4. Updated AGENTS.md: Changelog Annotation

Added "later removed (v0.5+)" suffix to the v0.6.2 changelog entry about the Grep PreToolUse hook, so the history is accurate without misleading readers into thinking the hook is still active.

## Verification

- Confirmed `suggest-recon.sh` no longer exists on disk
- Confirmed AGENTS.md skills table now has exactly 3 entries (matching `.claude-plugin/skills/` directory)
- Confirmed AGENTS.md hooks description matches `hooks.json` registrations
- Confirmed changelog annotation is present at the correct line

## Files Changed

| File | Action |
|------|--------|
| `.claude-plugin/hooks/suggest-recon.sh` | Deleted |
| `AGENTS.md` | Edited (3 locations) |
