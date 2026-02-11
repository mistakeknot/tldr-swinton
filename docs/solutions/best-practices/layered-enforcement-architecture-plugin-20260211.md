---
module: Plugin
date: 2026-02-11
problem_type: best_practice
component: integration
symptoms:
  - "Single-layer skill enforcement unreliable — agents ignore guidance"
  - "Preset names describing intensity (efficient/aggressive) are ambiguous"
  - "PostToolUse Bash command parsing fails on piped/compound commands"
  - "sys.argv not checked — argparse defaults block preset application"
root_cause: missing_workflow_step
resolution_type: workflow_improvement
severity: high
tags: [defense-in-depth, layered-enforcement, plugin-architecture, presets, hooks, skills]
---

# Best Practice: 4-Layer Defense-in-Depth for Agent Tool Adoption

## Problem

When building a CLI tool that agents should use for token savings, relying on a single enforcement mechanism (skills that recommend using the tool) is unreliable. Agents may ignore skill guidance, use the tool without optimal flags, or skip it entirely for familiar patterns like raw Read/Grep. A robust adoption strategy needs multiple layers that degrade gracefully.

## Environment
- Module: Plugin (.claude-plugin/)
- Affected Component: CLI presets, skills (SKILL.md), hooks (PreToolUse/PostToolUse), CLI hint emission
- Date: 2026-02-11

## Symptoms
- Agents read large files raw (1000+ lines) even when a skill suggests running `tldrs extract` first
- Agents run `tldrs context` without compression flags, consuming 3-5x more tokens than necessary
- Preset names like `efficient` and `aggressive` cause agents to hesitate or pick wrong presets
- PostToolUse Bash hooks that parse command text fail on `uv run tldrs`, pipes, compound commands
- `apply_preset()` checking `current is None or current is False` doesn't work because argparse sets string defaults (e.g., `format="text"`) that are neither None nor False — blocks preset from applying format

## What Didn't Work

**Attempted Solution 1:** Skills-only enforcement with per-file rules like "Never Read >100 lines without extract first"
- **Why it failed:** Skills require agent cooperation. They're loaded at trigger match time and followed at the agent's discretion. An agent focused on a quick fix often skips the skill guidance entirely. Zero enforcement guarantees.

**Attempted Solution 2:** PostToolUse Bash hook to detect tldrs commands and suggest presets
- **Why it failed:** Bash commands are free-form text. Detecting `tldrs` across `uv run tldrs`, `cd /tmp && tldrs context`, `tldrs context foo | head -20` requires robust parsing impossible within a 3-second hook timeout. False positives and negatives erode trust.

**Attempted Solution 3:** `apply_preset()` using `current is None or current is False` to detect explicit flags
- **Why it failed:** argparse sets defaults like `format="text"` for distill. These are neither None nor False, so the preset's `format="ultracompact"` never applies. Need `sys.argv` inspection to distinguish "user typed --format text" from "argparse set format to text by default."

## Solution

### Layer 1: CLI Presets (Foundation)

Make the token-saving path the easy path. One flag replaces 6+.

```python
# src/tldr_swinton/presets.py
PRESETS = {
    "compact": {                    # Name describes output shape
        "format": "ultracompact",
        "budget": 2000,
        "compress_imports": True,
        "strip_comments": True,
    },
    "minimal": {                    # Not "aggressive" — describes result
        "format": "ultracompact",
        "budget": 1500,
        "compress": "two-stage",
        "compress_imports": True,
        "strip_comments": True,
        "type_prune": True,
    },
}

# Explicit flag detection via sys.argv, not argparse defaults
def _is_explicit(key: str) -> bool:
    flag = f"--{key.replace('_', '-')}"
    return any(a == flag or a.startswith(f"{flag}=") for a in sys.argv[1:])
```

### Layer 2: Skills (Session Strategy)

Decision trees for which workflow to follow — NOT per-file rules.

```markdown
## Decision Tree
### 1. Are there recent changes?
**YES:** `tldrs diff-context --project . --preset compact`
**NO:** `tldrs structure src/`
```

Skills should never duplicate what hooks enforce. No "Never Read >100 lines" rules.

### Layer 3: Hooks (Per-File Tactics)

Zero-cooperation enforcement. Works even if agent ignores all skills.

```bash
# PostToolUse Read hook — fires AFTER Read on code files >300 lines
# Returns {additionalContext: "tldrs extract output..."} as JSON
# Per-file flag prevents duplicates: /tmp/tldrs-extract-{session_id}-{file_hash}
```

Key: PostToolUse (not PreToolUse) so the agent gets both the raw file content AND the structure summary without blocking.

### Layer 4: CLI Self-Hints

The CLI itself emits hints when run without presets — no hook parsing needed.

```python
def emit_preset_hint(command: str, args) -> None:
    if command in ("context", "diff-context") and not getattr(args, "preset", None):
        print("hint: Add --preset compact for 50%+ token savings", file=sys.stderr)
```

Agent sees the hint naturally in Bash output. Works with `uv run`, pipes, any invocation style.

## Why This Works

1. **Defense in depth.** Each layer catches what the previous missed. Skip skills? Hooks still work. Skip hooks? CLI hints still appear. Use preset? All flags applied correctly.

2. **No cooperation required for tactics.** Hooks fire automatically — the agent gets extract output and diff-context whether it asked for them or not.

3. **Single enforcement point per behavior.** Extract auto-inject = hooks only (not also skills). Workflow selection = skills only (not also hooks). No redundancy, no conflicts.

4. **Self-documenting names.** `compact` tells an agent "output will be small." `efficient` tells nothing — efficient at what? Names work in help text without explanation.

5. **sys.argv inspection.** Correctly distinguishes "user typed --format text" from "argparse set format to text by default," enabling presets to override defaults without overriding explicit choices.

## Prevention

- **Before adding a skill rule:** Check if a hook already enforces the same behavior. If yes, don't duplicate.
- **Before adding a hook:** Ask "does this need agent cooperation?" If yes, use a skill. If it should happen automatically, use a hook.
- **Before naming a preset/flag:** Ask "can an agent pick the right value from the name alone?"
- **Before parsing Bash commands in hooks:** Ask "can the CLI itself emit the hint?" Always more reliable.
- **Before checking argparse values:** Use `sys.argv` inspection for explicit flag detection, not `is None`/`is False` checks.

## Related Issues

- See also: [hooks-vs-skills-separation-plugin-20260211.md](hooks-vs-skills-separation-plugin-20260211.md) — the design principles this architecture implements
- See also: [cli-plugin-low-agent-adoption-vs-mcp-20260211.md](cli-plugin-low-agent-adoption-vs-mcp-20260211.md) — the broader adoption problem
- See also: [claude-code-hook-stdin-api.md](../integration-issues/claude-code-hook-stdin-api.md) — hook I/O constraints
