---
module: Plugin
date: 2026-02-11
problem_type: integration_issue
component: integration
symptoms:
  - "Agents read files directly without using tldrs despite plugin hooks being installed"
  - "PreToolUse nudge hook fires once per session and is easily ignored"
  - "Agents use basic tldrs flags instead of token-saving combinations like --compress two-stage --format ultracompact"
  - "Skills rely on agent choosing to invoke them — no enforcement of tldrs usage"
root_cause: wrong_api
resolution_type: workflow_improvement
severity: high
tags: [mcp, agent-adoption, token-savings, cli-vs-mcp, tool-descriptions, qmd]
---

# Integration Pattern: CLI+Plugin vs MCP for Agent Tool Adoption

## Problem

tldrs has 23 subcommands and 10+ token-saving strategies, but agents in practice only use a fraction of them. The plugin provides 6 skills, 6 slash commands, and 2 PreToolUse hooks, yet agents routinely bypass tldrs to read files directly or use basic flags without compression/format optimizations. The gap between "what tldrs can do" and "what agents actually use" is significant.

## Environment
- Module: Plugin (.claude-plugin/)
- Framework Version: 0.6.2
- Affected Component: Claude Code plugin hooks, skills, and CLI integration
- Date: 2026-02-11

## Symptoms
- Agents read code files directly (Read tool) without running `tldrs extract` or `tldrs diff-context` first
- The PreToolUse hook on Read/Grep fires once per session, outputs a tip via `additionalContext`, then goes silent — easily ignored
- When agents do use tldrs, they use basic invocations (e.g., `tldrs context foo`) without `--compress`, `--format ultracompact`, `--budget`, or `--session-id`
- Skills are "opt-in" — Claude must choose to invoke them based on trigger patterns, and often doesn't
- No enforcement or escalation ladder guiding agents from cheap to expensive operations

## Comparison: qmd's MCP-First Approach

**qmd** (github.com/tobi/qmd) solves the same adoption problem with a fundamentally different architecture:

| Aspect | qmd (MCP) | tldrs (CLI+Plugin) |
|--------|-----------|-------------------|
| **Presence** | Always-on MCP server — tools in agent's palette from session start | CLI behind Bash tool — agent must remember syntax |
| **Context injection** | `buildInstructions()` dynamically injects collection stats, capability warnings, and escalation ladder into every session | Setup hook prints a static tip once at session start |
| **Escalation ladder** | Baked into tool descriptions: search (~30ms) → vsearch (~2s) → deep_search (~10s) | Skills exist but agent picks arbitrarily with no cost guidance |
| **Interface style** | Declarative ("search for X, get Y") — agent calls a tool with parameters | Imperative ("run this CLI command with 6 flags") — high cognitive load |
| **Structured returns** | Always returns docid/score/snippet/context | Raw CLI text by default; `--machine` JSON available but rarely used |
| **Error guidance** | Tool returns helpful error + suggestion (e.g., "run `qmd embed` first") | CLI exits with error code; agent must interpret stderr |

## What Didn't Work

**Attempted Solution 1:** PreToolUse hooks that nudge agents with `additionalContext`
- **Why it failed:** Nudging is advisory — agents treat `additionalContext` as a suggestion, not an instruction. The one-shot flag file means the nudge only fires once, so agents that ignore it the first time never see it again.

**Attempted Solution 2:** Six autonomous skills with broad trigger patterns
- **Why it failed:** Skills depend on Claude's skill-matching heuristics. If the user says "fix the bug in auth.py", Claude may jump straight to reading the file rather than triggering `tldrs-session-start`. The triggers are broad but not mandatory.

**Attempted Solution 3:** Setup hook emitting usage guidance at session start
- **Why it failed:** Setup guidance gets compressed away as conversation lengthens. It's also static — doesn't adapt to what the agent is actually doing.

## Solution

Three architectural improvements, ranked by impact:

### 1. MCP Server (`tldrs mcp`) — Highest Impact

Build a `tldrs mcp` command that exposes key operations as MCP tools with self-documenting descriptions containing escalation guidance:

```
# Tool descriptions teach agents when/how to use each tool:
- tldrs_extract: "Get file structure (functions, classes, imports) — 85% fewer tokens than reading raw. Use BEFORE Read tool."
- tldrs_context: "Get call graph context around a symbol — signatures, callers, callees. Costs ~200 tokens vs ~2000 for reading the file."
- tldrs_diff_context: "Get token-efficient context for recent changes. Start here for any task involving modified code."
- tldrs_find: "Semantic code search by meaning. Prefer over Grep for concept-level queries."
```

Key design: `buildInstructions()` (like qmd) injects dynamic project context — index status, available compression modes, session-id for delta mode.

### 2. Flag Presets — Medium Impact

Reduce cognitive load by offering named presets instead of flag combinations:

```bash
tldrs context foo --preset efficient     # --format ultracompact --budget 2000 --compress-imports --strip-comments
tldrs diff-context --preset aggressive   # --compress two-stage --budget 1500 --format ultracompact
tldrs context foo --preset multi-turn    # --session-id auto --delta --format cache-friendly
```

MCP tool descriptions can reference presets: "Use `preset: efficient` for routine lookups, `preset: aggressive` for large diffs."

### 3. Smarter Hooks — Lower Impact (but quick win)

Instead of one-shot nudge, hooks that provide escalating guidance:
- First Read: suggest `tldrs extract` for the same file
- Second Read of same directory: suggest `tldrs structure` for the directory
- Third+ Read: suggest `tldrs diff-context` for the whole project
- Track which tldrs features the agent has used and suggest unused ones

## Why This Works

1. **MCP tools are always visible** — unlike CLI commands that agents must recall from memory or skill instructions, MCP tools appear in the tool palette every turn. The agent literally cannot forget they exist.

2. **Tool descriptions are the documentation** — qmd proves that well-written tool descriptions with cost hints ("~30ms", "~2s") and escalation guidance ("start with search, escalate to deep_search") are more effective than separate skill instructions that get compressed away.

3. **Declarative > Imperative for agents** — calling `tldrs_context(symbol="foo", budget=2000, format="ultracompact")` is easier for an LLM than constructing `tldrs context foo --project . --depth 2 --budget 2000 --format ultracompact`. Parameters with defaults handle the flag combinatorics.

4. **Dynamic instructions adapt** — `buildInstructions()` can inject "this project has 150 Python files, semantic index is ready, last diff touched 3 files" — giving agents situational awareness that static setup hooks cannot.

## Prevention

- **When adding new tldrs features:** Always ask "how will an agent discover and correctly use this?" If the answer requires reading docs or remembering flags, add an MCP tool or preset.
- **Tool description quality matters more than documentation** — agents read tool descriptions every turn but documentation only when triggered by a skill.
- **Test with naive agents** — verify that an agent with no prior tldrs knowledge, but with the MCP server connected, naturally uses tldrs for token savings.

## Related Issues

- See also: [claude-code-hook-stdin-api.md](claude-code-hook-stdin-api.md) — hook I/O constraints that limit what PreToolUse hooks can do
- See also: [plugin-version-drift-breaks-loading.md](../build-errors/plugin-version-drift-breaks-loading.md) — plugin delivery reliability affects whether hooks/skills load at all
