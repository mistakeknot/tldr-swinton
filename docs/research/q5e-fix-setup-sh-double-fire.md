# q5e: Fix setup.sh Double-Fire of diff-context

## Problem

The setup hook (`.claude-plugin/hooks/setup.sh`) and the `tldrs-session-start` skill BOTH executed `tldrs diff-context`, producing ~1,000-2,000 tokens of identical output every session start. This was pure waste: the same diff-context data appeared twice in the session context window, once from the setup hook and once from the skill.

## Root Cause

The setup hook (lines 51-63) contained a conditional block that ran `tldrs diff-context --project . --preset compact` when there were uncommitted changes (`CHANGED_COUNT > 0`), falling back to `tldrs structure` only on failure or clean trees. Meanwhile, the `tldrs-session-start` skill independently runs diff-context as its primary responsibility. Both fire at session start.

## Changes Made

All changes confined to `/root/projects/tldr-swinton/.claude-plugin/hooks/setup.sh`:

### 1. Removed diff-context execution (lines 51-63)

**Before:**
```bash
# --- Attempt to run tldrs diff-context or structure ---
TLDRS_OUTPUT=""
if [ "$CHANGED_COUNT" -gt 0 ]; then
    TLDRS_OUTPUT=$(timeout 7 tldrs diff-context --project . --preset compact 2>/dev/null)
    if [ $? -ne 0 ] || [ -z "$TLDRS_OUTPUT" ]; then
        TLDRS_OUTPUT=$(timeout 3 tldrs structure src/ 2>/dev/null || true)
    fi
else
    TLDRS_OUTPUT=$(timeout 5 tldrs structure src/ 2>/dev/null || true)
fi
```

**After:**
```bash
# --- Lightweight project structure (diff-context is handled by session-start skill) ---
TLDRS_OUTPUT=""
TLDRS_OUTPUT=$(timeout 5 tldrs structure src/ 2>/dev/null || true)
```

The 13-line conditional block with diff-context primary path and structure fallback was replaced with a 3-line unconditional `tldrs structure` call. The session-start skill now exclusively owns diff-context execution.

### 2. Updated fallback message (lines 79-81)

**Before:**
```bash
echo "Run 'tldrs diff-context --project . --preset compact' before reading code."
echo "Use 'tldrs extract <file>' for file structure."
```

**After:**
```bash
echo "The tldrs-session-start skill will run diff-context when you begin coding."
```

Points users to the skill rather than suggesting manual diff-context invocation.

### 3. Removed "Available presets" line (line 84)

**Removed:**
```bash
echo "Available presets: compact, minimal, multi-turn"
```

Redundant information -- Claude Code already knows preset names from the MCP tool descriptions.

### 4. Updated header comment (line 3)

**Before:** `# Runs at session start. Auto-runs diff-context and injects output.`
**After:** `# Runs at session start. Provides lightweight project summary.`

### 5. Updated fallback chain comment (line 4)

**Before:** `# Fallback chain: diff-context -> structure -> static tip`
**After:** `# Fallback chain: structure -> static tip`

This was a stale comment left from the original design that no longer reflected the actual behavior after removing diff-context.

## Token Savings

- **Per session:** ~1,000-2,000 tokens saved (one fewer diff-context output)
- **Setup hook is faster:** No longer waits up to 7 seconds for diff-context; structure completes in <1s typically
- **Cleaner separation of concerns:** Setup hook = project summary; session-start skill = diff analysis

## Responsibility Split After This Change

| Component | Responsibility |
|-----------|---------------|
| `setup.sh` (Setup hook) | Lightweight project summary: file counts, index status, changed files list, structure overview |
| `tldrs-session-start` (Skill) | Full diff-context analysis when coding begins |

## Files Changed

- `/root/projects/tldr-swinton/.claude-plugin/hooks/setup.sh` -- all 5 edits above
