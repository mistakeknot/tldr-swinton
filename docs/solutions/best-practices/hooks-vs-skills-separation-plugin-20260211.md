---
module: Plugin
date: 2026-02-11
problem_type: best_practice
component: integration
symptoms:
  - "Skill rule and hook both enforce the same behavior, causing redundant tldrs extract calls"
  - "Agent follows skill rule to run extract before Read, then hook also auto-runs extract during Read"
  - "Preset names efficient and aggressive are ambiguous — agents cannot pick the right one from name alone"
  - "PostToolUse Bash hook fails to reliably detect tldrs commands in piped or compound shell commands"
root_cause: logic_error
resolution_type: workflow_improvement
severity: high
tags: [plugin-design, hooks-vs-skills, separation-of-concerns, preset-naming, agent-adoption]
---

# Best Practice: Hooks for Per-File Tactics, Skills for Session Strategy

## Problem

When designing a Claude Code plugin that guides agent behavior, two mechanisms are available: **hooks** (fire automatically on tool use events) and **skills** (loaded when Claude matches trigger patterns). If both mechanisms target the same action — e.g., a skill rule saying "Never Read >100 lines without running extract first" AND a hook that auto-injects extract output on every large Read — they conflict. The agent gets redundant output, contradictory guidance, and the design becomes harder to reason about.

## Environment
- Module: Plugin (.claude-plugin/)
- Affected Component: Plugin hooks (PreToolUse/PostToolUse), skills (SKILL.md), CLI presets
- Date: 2026-02-11

## Symptoms
- Agent follows skill rule to run `tldrs extract` before a Read, then the PreToolUse hook also runs `tldrs extract` during the same Read — double extract output
- Skills contain per-file directives ("Never Read >100 lines without extract") that the hook already enforces automatically — the skill rule is redundant noise
- Preset names like `efficient` and `aggressive` describe intensity, not output shape — agents can't pick the right one without memorizing a table
- PostToolUse Bash hooks that parse command strings to detect tldrs usage fail on `uv run tldrs`, piped commands, compound commands

## What Didn't Work

**Attempted Solution 1:** Both skill rules AND hooks enforce the same per-file behavior
- **Why it failed:** Creates redundant enforcement. If the hook does it automatically, the skill rule is dead weight. If the agent follows the skill rule first, the hook fires anyway and produces duplicate output. The two mechanisms fight rather than complement.

**Attempted Solution 2:** PostToolUse hook on Bash to detect tldrs commands and nudge toward presets
- **Why it failed:** Bash commands are free-form text. Detecting `tldrs` reliably across `uv run tldrs`, `cd /tmp && tldrs`, `tldrs context foo | head -20` requires robust parsing that a 3-second hook timeout cannot accommodate. False positives and negatives erode trust.

## Solution

### Principle: Clean Separation of Enforcement Layers

**Hooks handle per-file tactical enforcement** — actions that should happen automatically on every relevant tool call, requiring zero agent cooperation:
- PreToolUse on Read (files >300 lines): auto-inject `tldrs extract` output as `additionalContext`
- Setup hook: auto-run `tldrs diff-context` and return output at session start
- These work whether or not the agent "chose" to use tldrs

**Skills handle session-level strategic guidance** — decision trees for which workflow to follow, not per-file rules:
- "Are there recent changes? → Use diff-context. Clean repo? → Use structure."
- "Multi-turn task? → Add --session-id auto to all calls."
- "Need to understand a symbol before editing? → Use tldrs impact."
- Skills should NOT duplicate what hooks already enforce

### Principle: Preset Names Describe Output Shape, Not Intensity

```
# Bad — describes how much compression (ambiguous):
--preset efficient    # every preset is "efficient"
--preset aggressive   # aggressive how? what's lost?

# Good — describes what the output looks like:
--preset compact      # stripped, compressed, budget-capped
--preset minimal      # maximally compressed, essentials only
--preset multi-turn   # optimized for repeated queries (already good)
```

An agent should pick the right preset from its name alone, without memorizing what flags each expands to.

### Principle: CLI Self-Hints Beat PostToolUse Command Parsing

Instead of a fragile PostToolUse hook parsing Bash commands:

```python
# In tldrs CLI itself — emit hint to stderr when run without --preset
if command in ("context", "diff-context") and not args.preset:
    print("hint: Add --preset compact for 50%+ token savings", file=sys.stderr)
```

The agent sees the hint in Bash output naturally. No hook complexity, no command parsing, works with `uv run`, pipes, compound commands.

## Why This Works

1. **No cooperation required for tactics.** Hooks fire automatically — the agent gets extract output, diff-context at session start, and CLI hints whether it asked for them or not. This is the claude-mem pattern: automatic capture beats asking for cooperation.

2. **Skills stay focused on strategy.** When skills don't repeat what hooks enforce, they become shorter, clearer decision trees. An agent reading a skill sees "here's the workflow to follow" not "here's a list of rules, some of which are already handled for you."

3. **Single enforcement point per behavior.** When only one mechanism handles each concern, there's no redundancy, no conflicts, and debugging is simpler. If extract output is wrong, you fix the hook. If the wrong workflow was chosen, you fix the skill.

4. **Self-documenting names reduce cognitive load.** `compact` tells an agent "the output will be small." `efficient` tells an agent nothing — efficient at what? Behavior-descriptive names work in help text, error messages, and skill instructions without additional explanation.

## Prevention

- **Before adding a skill rule:** Check if a hook already enforces the same behavior. If yes, don't duplicate it in the skill.
- **Before adding a hook:** Ask "does this need agent cooperation or should it happen automatically?" If automatic, use a hook. If it requires the agent to make a strategic choice, use a skill.
- **Before naming a preset/flag:** Ask "can an agent pick the right value from the name alone?" If it needs to read a table, the name is wrong.
- **Before adding PostToolUse Bash parsing:** Ask "can the CLI itself emit the hint?" If yes, that's always more reliable.

## Related Issues

- See also: [cli-plugin-low-agent-adoption-vs-mcp-20260211.md](cli-plugin-low-agent-adoption-vs-mcp-20260211.md) — the broader adoption problem this principle addresses
- See also: [claude-code-hook-stdin-api.md](claude-code-hook-stdin-api.md) — hook I/O constraints
- See also: [layered-enforcement-architecture-plugin-20260211.md](layered-enforcement-architecture-plugin-20260211.md) — full 4-layer implementation of these principles
