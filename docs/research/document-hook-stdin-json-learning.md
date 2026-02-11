# Claude Code Hook Scripts: stdin JSON API Learning Document

**Date:** 2026-02-08
**Category:** Integration Research
**Status:** Complete
**Session:** Bug discovery and root-cause analysis of PreToolUse hook stdin API

---

## Problem Statement

A Claude Code PreToolUse hook script (`suggest-recon.sh`) was generated with two critical bugs:

1. **Wrong Session Persistence**: Used `$$` (PID of bash subprocess) as a stable session identifier
   - Problem: `$$` changes every hook invocation — the flag file is never found on subsequent calls
   - Result: Hook always re-runs and re-prints the nudge message, instead of nudging only once per session

2. **Wrong Input Method**: Attempted to read tool input from `CLAUDE_TOOL_INPUT_file_path` environment variable
   - Problem: This environment variable does not exist in the hook execution context
   - Result: `FILE` variable was always empty, file filtering never worked

Both issues stem from a fundamental misconception: **Claude Code hooks do not receive tool input as environment variables — they receive it as JSON on stdin.**

---

## Root Cause Analysis

### Hook Execution Model

Claude Code hooks are executed as **separate bash processes** that receive:
- **Input**: JSON object on stdin containing hook metadata and tool input
- **Output**: stdout/stderr for logging/nudging
- **Exit code**: Determines whether to proceed with the tool

The hook lifecycle:
1. Claude Code detects a tool invocation (e.g., `Read`)
2. Matches PreToolUse hook matchers against the tool name
3. Spawns bash process with hook script
4. **Passes full hook context as JSON to stdin**
5. Hook reads stdin, parses JSON, executes logic
6. Hook exits; Claude Code continues tool execution

### Official Hook Input Schema (PreToolUse)

Based on the working `suggest-recon.sh` implementation, the stdin JSON structure is:

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

**Key fields for tool input access:**
- `tool_input.*`: Nested object containing the tool's parameters
- `session_id`: Stable identifier that persists for entire conversation
- `tool_name`: String like "Read", "Grep", "Write" — used for hook matching

### Why Environment Variables Don't Work

The hook runs in a **clean bash subprocess** with minimal environment. Claude Code does NOT set environment variables like `CLAUDE_TOOL_INPUT_file_path`. This design choice:
- Isolates hooks from session environment pollution
- Forces explicit JSON parsing (prevents accidental parsing mistakes)
- Makes input schema versioning explicit (JSON schema evolution is cleaner)

---

## Working Solution

### Pattern: Read stdin Once, Parse with jq

```bash
#!/bin/bash
# Read entire stdin into variable (JSON is single-line in practice)
INPUT=$(cat)

# Extract session_id for stable session-scoped state
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
if [ -z "$SESSION_ID" ]; then
    exit 0  # Skip if no session ID available
fi

# Use session_id in flag file path (stable across calls)
FLAG="/tmp/tldrs-session-${SESSION_ID}"

# Skip if already nudged this session
[ -f "$FLAG" ] && exit 0

# Extract tool input (nested under .tool_input.<field_name>)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# Process file...
[ -f "$FILE" ] && wc -l "$FILE"

# Mark this session as nudged
touch "$FLAG"
```

### Critical Implementation Details

1. **Read stdin exactly once**
   - `INPUT=$(cat)` captures all stdin at once
   - Avoid reading stdin multiple times — it may not be seekable
   - Use `echo "$INPUT" | jq` to parse repeatedly from the captured string

2. **Use `session_id` from JSON, not `$$`**
   - `session_id` is a stable UUID/identifier provided by Claude Code
   - Persists for entire conversation (multiple hook invocations)
   - `$$` changes every bash subprocess invocation — **never use for persistence**

3. **Access tool input via `.tool_input.<field>`**
   - Tool parameters are nested under `tool_input` key
   - For Read tool: `.tool_input.file_path` is the file to be read
   - For other tools: check what fields are in `tool_input`
   - Use jq's `// ""` to provide safe defaults

4. **Prefer `jq -r` for string values**
   - `jq -r` returns raw strings without quotes
   - `-r` is critical for bash variable assignment
   - Without `-r`, you get JSON strings like `"path"` (with quotes), not `path`

---

## Discovery Process

### How This Was Found

A subagent (Explore type) investigated the hook API mismatch by:

1. **Examining the working hook implementation** (`suggest-recon.sh`)
   - Found `INPUT=$(cat)` pattern
   - Found `jq -r '.session_id'` parsing
   - Realized stdin was the input method

2. **Cross-referencing with Python hooks**
   - Located `hookify/pretooluse.py` in Claude Code internal code
   - Observed `json.load(sys.stdin)` — confirms stdin carries JSON
   - Noted Python hooks use identical schema

3. **Checking other hook implementations**
   - Found `tool-time/hook.sh` (another Claude Code plugin)
   - Verified it uses identical `INPUT=$(cat) | jq` pattern
   - Confirmed best practice across multiple plugins

4. **Reviewing Claude Code documentation**
   - Found official hooks reference (though not publicly indexed)
   - Confirmed stdin JSON is the documented input method
   - Noted environment variables are not supported for tool input

### Key Artifacts Examined

| Artifact | Finding |
|----------|---------|
| `tldr-swinton/.claude-plugin/hooks/suggest-recon.sh` | Working reference implementation |
| `tldr-swinton/.claude-plugin/hooks/hooks.json` | Hook definition + matcher config |
| Python hooks (internal) | Confirms `json.load(sys.stdin)` pattern |
| tool-time plugin hooks | Identical stdin+jq pattern in other plugins |
| Claude Code official docs | stdin JSON documented as input method |

---

## Prevention Strategies

### For Future Hook Development

1. **Always start with a known working example**
   - Reference existing Claude Code plugin hooks
   - `tool-time` and `interagency-marketplace` plugins have good examples
   - Copy the `INPUT=$(cat) | jq` pattern as boilerplate

2. **Test hook scripts in isolation**
   - Simulate stdin JSON manually:
     ```bash
     echo '{"session_id":"test-123","tool_name":"Read","tool_input":{"file_path":"/tmp/test.txt"}}' | bash suggest-recon.sh
     ```
   - Verify flag file is created and reused
   - Verify file filtering works as expected

3. **Document assumptions about input**
   - Add a comment at top of hook script showing example stdin JSON
   - Document which fields are required vs optional
   - Reference the official hook schema

4. **Never use `$$` for persistence**
   - `$$` is the PID of current bash process — changes every execution
   - Use `session_id` from hook JSON for session-scoped state
   - Use `${RANDOM}` or UUIDs only if you need truly unique ephemeral identifiers

5. **Never assume CLAUDE_TOOL_INPUT_* environment variables**
   - These do not exist
   - All tool input comes via stdin JSON
   - Check `tool_input` key in the parsed JSON object

---

## Lesson Recorded

### One-Line Summary
Claude Code hooks receive input as **JSON on stdin** (via `session_id`, `tool_input`, etc.), not as environment variables or shell parameters — use `INPUT=$(cat) | jq` for parsing.

### Why This Matters
- Prevents duplicate flag files and repeated nudges due to using `$$` instead of `session_id`
- Ensures file filtering and tool input access work correctly
- Enables session-scoped state management (e.g., "nudge only once per session")

### When This Applies
- Writing PreToolUse, PostToolUse, or Setup hook scripts for Claude Code plugins
- Passing any kind of context or tool input data to hook scripts
- Managing session-scoped state in hooks

### Key Gotchas
1. `$$` is the PID of the bash subprocess running the hook — it changes every invocation
2. Environment variables like `CLAUDE_TOOL_INPUT_file_path` do not exist
3. `jq` output needs `-r` flag to get raw strings (without JSON quotes)
4. stdin is single-read only — capture with `$(cat)` first, then pipe to jq repeatedly

---

## Technical Details: Hook Input Schema Reference

### PreToolUse Hook Input (Complete Schema)

```json
{
  "session_id": "uuid-string-unique-per-conversation",
  "transcript_path": "absolute-path-to-conversation-jsonl",
  "cwd": "absolute-current-working-directory",
  "hook_event_name": "PreToolUse",
  "tool_name": "ToolName",
  "tool_input": {
    "field1": "value1",
    "field2": "value2",
    ...
  }
}
```

### Tool-Specific Input Examples

**Read Tool:**
```json
{
  "tool_input": {
    "file_path": "/path/to/file.txt"
  }
}
```

**Grep Tool:**
```json
{
  "tool_input": {
    "pattern": "regex-pattern",
    "path": "/search/path",
    "type": "py"
  }
}
```

**Bash Tool:**
```json
{
  "tool_input": {
    "command": "ls -la /tmp",
    "description": "List /tmp directory"
  }
}
```

---

## References & Context

- **Working Implementation**: `/root/projects/tldr-swinton/.claude-plugin/hooks/suggest-recon.sh`
- **Hook Definition**: `/root/projects/tldr-swinton/.claude-plugin/hooks/hooks.json`
- **Related Tools**: `tool-time` plugin, `interagency-marketplace` plugin
- **Internal Reference**: hookify/pretooluse.py (Claude Code internal)
- **Date Discovered**: 2026-02-08
- **Status**: Documented and deployed in suggest-recon.sh

---

## Conclusion

Claude Code hook scripts receive input exclusively via **JSON on stdin**, not environment variables or parameters. The working pattern is:

```bash
INPUT=$(cat)
FIELD=$(echo "$INPUT" | jq -r '.path.to.field // ""')
```

Key points:
- `session_id` from JSON is stable per conversation (use for persistence)
- `$$` is unstable (PID changes every subprocess)
- `tool_input.*` contains the tool's actual parameters
- Environment variables like `CLAUDE_TOOL_INPUT_*` do not exist
- Always use `jq -r` to get raw strings, not JSON-quoted strings
