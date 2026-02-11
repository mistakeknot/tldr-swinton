---
title: "Codex dispatch.sh Fails in Bash Tool Background Mode"
category: integration-issues
tags: [codex, dispatch, interclode, background, bash-tool, argument-parsing, shell-quoting]
module: interclode/dispatch.sh
severity: medium
date_solved: 2026-02-08
status: solved
---

# Codex dispatch.sh Fails in Bash Tool Background Mode

## Problem Statement

When dispatching Codex CLI agents via `interclode/dispatch.sh` using Claude Code's Bash tool with `run_in_background: true`, all dispatch commands fail consistently with:

```
Error: No prompt provided
Usage: dispatch.sh -C <dir> -o <output> [OPTIONS] "prompt"
       dispatch.sh --prompt-file <file> [OPTIONS]
```

**Key observations:**
- The same commands execute successfully in foreground mode (without `run_in_background`)
- Three separate batches of 3 agents each (9 total dispatches) all failed with identical errors
- The `--prompt-file` flag was never matched by the argument parser's `case "$1" in` statement

## Root Cause Analysis

The Bash tool's background mode handles argument passing differently than foreground mode. The exact mechanism is unclear and likely involves one or more of:

1. **Shell quoting/escaping differences** - Arguments may be re-quoted during backgrounding
2. **Heredoc expansion timing** - If dispatch.sh uses heredocs, background mode may expand them differently
3. **Process backgrounding mechanism** - The Bash tool may wrap background commands with `nohup`, `setsid`, or similar, affecting shell interpretation
4. **Double-shell wrapping** - The backgrounding layer may introduce an additional shell invocation, changing how arguments are parsed

### Evidence

- Bash trace (`bash -x`) output showed `--prompt-file` was never captured in the first positional parameter
- The case statement in dispatch.sh's argument parser never matched any of the conditional branches
- Direct foreground execution with identical arguments worked without modification
- This suggests the arguments arrive corrupted or missing at the script invocation layer

## Working Solution

**Use foreground Bash calls** with `timeout: 600000` (10 minutes) to allow sufficient execution time for Codex CLI operations to complete.

For parallel dispatch, issue **multiple independent foreground Bash tool calls in the same message**. Claude Code runs them concurrently anyway, achieving parallelism without background mode.

### Example: Parallel Foreground Dispatch

```bash
# Foreground, parallel via multiple tool calls (WORKS)
bash "$DISPATCH" --prompt-file /tmp/task1.md -C /root/project -o /tmp/out1.md -s workspace-write
bash "$DISPATCH" --prompt-file /tmp/task2.md -C /root/project -o /tmp/out2.md -s workspace-write
bash "$DISPATCH" --prompt-file /tmp/task3.md -C /root/project -o /tmp/out3.md -s workspace-write
```

Each Bash tool call blocks (foreground), but all three are issued simultaneously in the tool call block, so they run in parallel.

### Tool Configuration

```yaml
- command: bash "$DISPATCH" --prompt-file /tmp/task.md -C /project -o /tmp/out.md
  timeout: 600000  # 10 minutes - allow full Codex execution
  run_in_background: false  # CRITICAL: never use true
```

## Prevention & Best Practices

1. **Default to foreground Bash calls for dispatch.sh** - There is no known advantage to background mode; foreground with multiple concurrent tool calls achieves parallelism more reliably

2. **Only use `run_in_background: true` for simple, single-command operations** - Not for complex multi-flag command invocations like dispatch.sh

3. **If background mode is absolutely required**, pass the prompt as an inline positional argument instead of `--prompt-file`:
   ```bash
   # Inline (marginally more robust than --prompt-file in background)
   bash "$DISPATCH" -C /project -o /tmp/out.md -s workspace-write "$(cat /tmp/task.md)"
   ```

4. **Always test dispatch commands with `--dry-run` first**:
   ```bash
   bash "$DISPATCH" --prompt-file /tmp/task.md --dry-run
   ```
   This validates argument parsing without actually executing Codex, catching quoting issues early.

5. **Use explicit variable quoting in dispatch invocations**:
   ```bash
   # Good
   bash "$DISPATCH" --prompt-file "$PROMPT_FILE" -C "$PROJECT_DIR"

   # Avoid
   bash $DISPATCH --prompt-file $PROMPT_FILE -C $PROJECT_DIR
   ```

## Detailed Error Trace

When background mode fails, the dispatch.sh script receives malformed arguments:

```
$ bash -x dispatch.sh --prompt-file /tmp/task.md -C /project
+ case "$1" in
  (no match - $1 is empty or corrupted)
+ echo "Error: No prompt provided"
+ echo "Usage: ..."
```

The first positional parameter `$1` should be `--prompt-file` but appears empty or unrecognized. This indicates the argument vector is corrupted between tool invocation and script execution.

## Workaround: If Foreground Is Too Slow

If foreground execution times out (unlikely for well-scoped Codex tasks):

1. **Split tasks into smaller chunks** - Dispatch fewer agents per batch
2. **Increase timeout** - Set `timeout: 900000` (15 minutes)
3. **Use external orchestration** - Write a separate coordinator script that manages background dispatch instead of relying on the Bash tool's background mode

## Implementation Notes

For agent workflows using dispatch.sh:

1. **In agent-workflow.md**: Document that dispatch must use foreground mode
2. **In Bash tool calls**: Always set `run_in_background: false` (or omit, as it defaults to false)
3. **For parallelism**: Issue multiple Bash tool calls in the same block — Claude Code will run them concurrently
4. **Testing**: Verify dispatch.sh works in the development environment with `bash scripts/dispatch.sh --dry-run` before using in agent workflows

## Related Files

- `interclode/dispatch.sh` - The problematic dispatch script
- `.claude-plugin/commands/find.md` - CLI command dispatcher reference
- `docs/agent-workflow.md` - Agent workflow documentation
- `AGENTS.md` - Full architecture and agent coordination guide

## Lessons Learned

- **Bash tool background mode is not reliable for complex argument passing** — Use foreground with concurrent tool calls for parallelism
- **Argument corruption in background mode may fail silently** — The script executes but with wrong args; always validate inputs
- **Multiple concurrent foreground calls are faster than debugging background quoting** — Prefer simple, working patterns
- **Test argument-heavy scripts in both foreground and background** — Catch issues early in isolated environments

## Resolution Status

✅ **SOLVED** - Use foreground dispatch with multiple concurrent Bash tool calls. All 9 agents successfully dispatched using this pattern.

---

**Updated:** 2026-02-08
**Severity:** Medium (workaround exists, integration reliable in foreground)
**Impact:** All Codex dispatch workflows via Bash tool background mode
