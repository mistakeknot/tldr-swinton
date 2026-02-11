---
title: "Claude Code Hook Scripts Use stdin JSON, Not Environment Variables"
category: integration-issues
tags: [claude-code, hooks, PreToolUse, stdin, json, plugin, bash]
module: .claude-plugin/hooks
symptoms:
  - "Hook flag file never found on subsequent calls"
  - "Empty variable from CLAUDE_TOOL_INPUT_*"
  - "Session flag with $$ changes every hook invocation"
  - "File filtering silently fails (no output)"
severity: medium
date_solved: 2026-02-08
---

# Claude Code Hook Scripts: stdin JSON API, Not Environment Variables

## Problem

When writing a Claude Code plugin PreToolUse hook script (`suggest-recon.sh`), a subagent generated code with two critical bugs:

### Bug 1: Using `$$` for Session Persistence
```bash
# WRONG: $$ is the PID of current bash subprocess
FLAG="/tmp/tldrs-session-${$$}"
```

**Problem**: `$$` changes every hook invocation. Flag file is never found on subsequent calls.

**Result**: Hook re-runs every time instead of nudging only once per session.

### Bug 2: Reading from Non-Existent Environment Variable
```bash
# WRONG: CLAUDE_TOOL_INPUT_file_path does not exist
FILE="${CLAUDE_TOOL_INPUT_file_path}"
```

**Problem**: Claude Code does not set environment variables for tool input.

**Result**: `FILE` is always empty; file filtering never works.

---

## Root Cause

**Claude Code hooks do not receive tool input as environment variables.** Instead, they receive **JSON on stdin** containing:
- Session metadata (`session_id`, `cwd`, `transcript_path`)
- Hook event name
- Tool name and tool input parameters

### Official Hook Input Schema (PreToolUse)

```json
{
  "session_id": "abc123-def456-ghi789",
  "transcript_path": "/Users/.../.claude/projects/.../00893aaf.jsonl",
  "cwd": "/Users/...",
  "hook_event_name": "PreToolUse",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/path/to/file.txt"
  }
}
```

---

## Solution

### Pattern: Parse stdin JSON with jq

```bash
#!/bin/bash
# tldrs PreToolUse hook for Read

# Read stdin JSON (hook receives input as JSON on stdin, not env vars)
INPUT=$(cat)

# Extract session_id for stable session-scoped state
# session_id persists for entire conversation (unlike $$)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
if [ -z "$SESSION_ID" ]; then
    exit 0
fi

# Use session_id in flag file (stable across hook invocations)
FLAG="/tmp/tldrs-session-${SESSION_ID}"
[ -f "$FLAG" ] && exit 0

# Extract tool input via .tool_input.<field>
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# Process file...
if [ -f "$FILE" ]; then
    lines=$(wc -l < "$FILE" 2>/dev/null || echo 999)
    if [ "$lines" -ge 50 ]; then
        echo "tip: Run 'tldrs context' to save tokens"
    fi
fi

# Mark session as processed
touch "$FLAG"
```

### Critical Implementation Details

1. **Read stdin exactly once**
   ```bash
   INPUT=$(cat)  # Capture all stdin at once
   ```
   Stdin may not be seekable. Capture it into a variable first, then parse repeatedly with `jq`.

2. **Use `session_id` from JSON for persistence, not `$$`**
   ```bash
   # CORRECT: session_id is stable per conversation
   SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
   FLAG="/tmp/flag-${SESSION_ID}"

   # WRONG: $$ changes every subprocess
   FLAG="/tmp/flag-${$$}"
   ```

3. **Access tool input via `.tool_input.<field>`**
   ```bash
   # For Read tool:
   FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

   # For other tools, check .tool_input.<field_name>
   ```

4. **Always use `jq -r` for string extraction**
   ```bash
   # CORRECT: -r removes JSON quotes
   VAR=$(echo "$INPUT" | jq -r '.session_id')

   # WRONG: Without -r, VAR contains JSON quotes
   VAR=$(echo "$INPUT" | jq '.session_id')
   # Result: VAR='"abc123"' (with quotes!) not VAR='abc123'
   ```

---

## Complete Working Implementation

See the corrected hook script at:
- **File**: `/root/projects/tldr-swinton/.claude-plugin/hooks/suggest-recon.sh`
- **Deployed**: 2026-02-08

Highlights:
- Lines 8–10: Read stdin and extract session_id
- Lines 12–14: Use session_id for persistent flag
- Lines 24: Access tool_input.file_path from JSON
- No use of `$$` or `CLAUDE_TOOL_INPUT_*` environment variables

---

## Testing Your Hook Script

### Manual Test (Simulate Hook Input)

```bash
# Create sample stdin JSON
cat > /tmp/hook-input.json << 'EOF'
{
  "session_id": "test-session-001",
  "cwd": "/tmp",
  "hook_event_name": "PreToolUse",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/tmp/test.txt"
  }
}
EOF

# Run hook with simulated input
cat /tmp/hook-input.json | bash your-hook.sh
```

### Verify Session Persistence

```bash
# First call (should create flag)
cat /tmp/hook-input.json | bash your-hook.sh
echo "Return code: $?"  # Should be 0 or 1 depending on your logic

# Second call (flag should exist, hook should skip)
cat /tmp/hook-input.json | bash your-hook.sh
# Check if your flag file was used correctly
ls -la /tmp/flag-test-session-001
```

---

## Prevention Checklist

When writing Claude Code hook scripts:

- [ ] **Always parse stdin JSON**: `INPUT=$(cat)` at the start
- [ ] **Use `session_id` from JSON**: Not `$$` for persistence
- [ ] **Access tool input via `.tool_input.*`**: Not environment variables
- [ ] **Always use `jq -r`**: To get raw strings, not JSON-quoted strings
- [ ] **Provide jq defaults**: Use `// ""` to handle missing fields gracefully
- [ ] **Test with manual stdin injection**: Verify before deployment
- [ ] **Reference working examples**: Copy from `tool-time` or `interagency-marketplace` plugins

---

## Common Mistakes

| Mistake | Wrong | Correct |
|---------|-------|---------|
| Session persistence | `FLAG="/tmp/${$$}"` | `FLAG="/tmp/${SESSION_ID}"` where `SESSION_ID=$(echo "$INPUT" \| jq -r '.session_id')` |
| Tool input access | `FILE="${CLAUDE_TOOL_INPUT_file_path}"` | `FILE=$(echo "$INPUT" \| jq -r '.tool_input.file_path // ""')` |
| String parsing | `VAR=$(jq '.field')` | `VAR=$(jq -r '.field')` |
| Multiple stdin reads | Loop with `cat` multiple times | `INPUT=$(cat)` once, reuse in loops |

---

## Reference: Hook Input Schema

### PreToolUse Hook (Fires before tool execution)

```json
{
  "session_id": "unique-uuid-per-conversation",
  "transcript_path": "/path/to/conversation.jsonl",
  "cwd": "/current/working/directory",
  "hook_event_name": "PreToolUse",
  "tool_name": "ToolName",
  "tool_input": {
    "field1": "value1",
    "field2": "value2"
  }
}
```

### Tool-Specific Examples

**Read Hook:**
```bash
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path')
```

**Grep Hook:**
```bash
PATTERN=$(echo "$INPUT" | jq -r '.tool_input.pattern')
PATH=$(echo "$INPUT" | jq -r '.tool_input.path')
```

**Bash Hook:**
```bash
CMD=$(echo "$INPUT" | jq -r '.tool_input.command')
```

---

## Links

- **Source File**: `/root/projects/tldr-swinton/.claude-plugin/hooks/suggest-recon.sh`
- **Hook Definition**: `/root/projects/tldr-swinton/.claude-plugin/hooks/hooks.json`
- **Detailed Analysis**: `docs/research/document-hook-stdin-json-learning.md`
- **Reference Implementations**:
  - `tool-time` plugin hooks
  - `interagency-marketplace` plugin hooks
