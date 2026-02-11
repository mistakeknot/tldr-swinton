# Design: Maximize Agent tldrs Adoption for Token Savings

**Date:** 2026-02-11
**Status:** Revised — incorporates flux-drive review findings
**Problem:** tldrs has 23 subcommands and 10+ token-saving strategies, but agents only use a fraction. The gap between "what tldrs can do" and "what agents actually use" is the core problem.

## Success Metric

Measure the ratio of `tldrs` Bash calls to raw `Read` calls on files >300 lines across eval sessions. Target: >60% of large-file reads go through tldrs (extract, context, or diff-context) rather than raw Read.

## Context

### Current Integration Surface
- 6 skills (autonomous triggers), 6 slash commands, 2 PreToolUse hooks (Read/Grep), 1 Setup hook
- Hooks fire once per session (flag file), only nudge — don't block or auto-run tldrs
- Skills rely on Claude choosing to invoke them — no enforcement
- Many powerful features (delta mode, VHS refs, compression, zoom levels) have no skill or hook driving agents toward them

### Failure Modes (All observed)
1. Agents never trigger the skill — read files directly, hook nudge ignored
2. Agents trigger skill but use basic flags — no `--compress`, no `--format ultracompact`, no `--session-id`
3. Agents don't use tldrs for the right task — reading 500-line files raw when `tldrs extract` gives 90% of what's needed

### Reference Design: qmd (github.com/tobi/qmd)
qmd solves adoption through MCP with `buildInstructions()` for dynamic context injection, escalation ladders in tool descriptions, and declarative interfaces. Key insight: tool descriptions seen every turn beat documentation that gets compressed away.

### Reference Design: claude-mem (github.com/thedotmack/claude-mem)
claude-mem uses hooks for automatic capture (6 lifecycle hooks, no agent cooperation needed) and MCP for retrieval with 3-layer progressive disclosure (index ~50-100 tokens → timeline → full detail ~500-1000 tokens). 10x token savings through progressive disclosure.

### Ecosystem Finding: Hook State of the Art
Nobody has proven stateful escalating hooks work. Best hooks are binary — block dangerous operations, validate inputs, inject context at session start. Complex state machines across hook invocations are unproven.

---

## Design: Four Changes, Priority Order

### Change 1: CLI Flag Presets (`--preset`)

**Where:** `src/tldr_swinton/cli.py` (argparse-based CLI)

**Three presets — names describe output shape, not intensity:**

| Preset | Expands To | When to Use |
|--------|-----------|-------------|
| `compact` | `--format ultracompact --budget 2000 --compress-imports --strip-comments` | Default for any context/diff-context call |
| `minimal` | `--format ultracompact --budget 1500 --compress two-stage --compress-imports --strip-comments --type-prune` | Large diffs, big codebases, budget-constrained sessions |
| `multi-turn` | `--format cache-friendly --budget 2000 --session-id auto --delta` | Multi-turn conversations, re-querying same project |

> **Naming rationale:** `compact` tells an agent "the output will be small." `minimal` tells an agent "the output will be as small as possible." An agent can pick the right preset from its name alone. Previous names (`efficient`, `aggressive`) described intensity, not the output shape — `efficient` could mean anything.

**Behavior:**
- `--preset` sets defaults — explicit flags still override (e.g., `--preset compact --budget 3000` uses 3000)
- Valid on: `context`, `diff-context`, `distill` (token-heavy output commands that support `--format`, `--budget`, `--compress`)
- **Not valid on:** `extract` (extract has its own output format — it doesn't support `--format`, `--budget`, or `--compress`)
- Invalid preset → clear error listing available presets
- `tldrs presets` subcommand lists all presets with expansions (`--machine` for JSON)
- `session-id auto` → uses Claude Code's `$CLAUDE_SESSION_ID` env var if available, falls back to hash of CWD + git HEAD for stable session identity

**CLI self-hint — when run without `--preset`:**
```python
# In CLI output path, emit hint to stderr when no preset used
if command in ("context", "diff-context") and not args.preset:
    print("hint: Add --preset compact for 50%+ token savings", file=sys.stderr)
```
The agent sees the hint in Bash output naturally. No hook complexity, no command parsing. Works with `uv run`, pipes, compound commands.

**Example:**
```bash
# Before (6 flags):
tldrs diff-context --project . --format ultracompact --budget 2000 --compress-imports --strip-comments --compress two-stage

# After (1 flag):
tldrs diff-context --project . --preset minimal
```

---

### Change 2: Skill Rewrite — Decision Trees Over Man Pages

**Current problem:** Skills read like flag reference docs. Agents copy templates or fall back to raw Read when the template doesn't fit.

**New pattern:** Each skill becomes a decision tree. Skills handle **session-level strategy only** — per-file tactical enforcement (like auto-injecting extract output for large files) is handled by hooks (Change 4), not skill rules.

#### Example: `tldrs-session-start` (highest-traffic skill)

**Current:**
```
Run: tldrs diff-context --project . --budget 2000
Optional: add --compress two-stage for 35-73% savings
Optional: add --session-id task-name for multi-turn
```

**Proposed:**
```
BEFORE reading any code files, determine your starting point:

1. Are there recent changes? (git status shows modified files)
   YES → tldrs diff-context --project . --preset compact
   YES + large diff (>500 lines) → tldrs diff-context --project . --preset minimal
   NO  → tldrs structure src/

2. Will this be a multi-turn task?
   YES → add --session-id auto to ALL tldrs calls this session

3. After diff-context, identify your targets:
   - [contains_diff] symbols → read with tldrs context <symbol> --preset compact
   - [caller_of_diff] symbols → check for breakage with tldrs impact <symbol>
   - Unknown area? → tldrs find "query" before Reading files

4. Spawning a subagent for code work?
   → tldrs distill --task "description" --budget 1500 --session-id auto
   (compress context for sub-agent consumption)

RULE: Always use --preset compact unless you have a reason not to.
```

> **Note:** The old rule "Never Read >100 lines without running tldrs extract first" is removed from skills. The PostToolUse hook on Read (Change 4) handles this automatically — the agent gets extract output for free on large files without needing to cooperate. Skills focus on strategic decisions, hooks handle per-file tactics.

**Same pattern for all skills:**

| Skill | Key decision point | Strategic rule |
|-------|-------------------|----------------|
| `session-start` | Recent changes? → diff-context vs structure. Subagent? → distill | Always use --preset compact |
| `find-code` | Know name → structural. Know concept → semantic. Know text → regex | Always try tldrs find before Grep for code files |
| `understand-symbol` | Need callers → impact. Need callees → context. Both → context --depth 2. About to edit? → impact first | Always use --preset compact. Always check callers before modifying a public function |
| `explore-file` | Debugging → cfg+dfg. Structure → extract. Tracing → slice | Skip for files <100 lines |
| `map-codebase` | New repo → arch then structure. Known repo, new area → structure on subdir | Use tree only for orientation, structure for real work |

#### Skill Consolidation

The flux-drive review identified that two proposed new skills (`before-edit` and `handoff`) are better folded into existing skills rather than added as standalone:

- **`before-edit` → folded into `understand-symbol`**: The "about to edit" trigger already overlaps with "understanding a symbol." Adding "check callers before modifying a public function" as a decision branch in `understand-symbol` is cleaner than a separate skill that fires alongside it.

- **`handoff` → folded into `session-start`**: Subagent handoff is a session-start decision ("am I spawning a subagent?"), not a separate skill. Adding `tldrs distill` as a branch in `session-start` keeps all session-level workflow decisions in one place.

**Result: 6 skills (same count as today), all rewritten as decision trees.**

---

### Change 3: Setup Hook as Dynamic Briefing

**Current:** Static tip ("Run `tldrs diff-context`").

**Proposed:** Run `tldrs diff-context` automatically and inject the output as `additionalContext`.

**Behavior:**
1. Check `git diff --stat HEAD` — are there recent changes? (~instant)
2. If changes exist: run `tldrs diff-context --project . --preset compact` and capture output
3. If no changes: run `tldrs structure src/` instead (lightweight project overview)
4. Check `.tldrs/` directory — is semantic index ready? (~instant, file check)
5. Format as `additionalContext` JSON with the tldrs output embedded

**Output format (what the agent sees):**
```
Project: tldr-swinton (47 Python files, 3 changed since last commit)
Semantic index: ready (indexed 2h ago)

--- diff-context output below ---
[actual tldrs diff-context --preset compact output]

Available presets: compact, minimal, multi-turn
```

**Key design change from draft:** The setup hook **runs** `tldrs diff-context`, not just recommends it. This follows the claude-mem pattern — automatic capture beats asking for cooperation. The agent starts the session with diff context already loaded, zero cooperation required.

**Timeout consideration:** Setup hooks have a 10s timeout in Claude Code. `tldrs diff-context --preset compact` on a typical project completes in 2-4s. For large projects (>200 files changed), the hook falls back to `tldrs structure src/` which is always fast.

**Fallback chain:**
1. `tldrs diff-context` succeeds → inject output
2. `tldrs diff-context` times out or fails → try `tldrs structure src/`
3. `tldrs structure` fails → fall back to static tip (current behavior)
4. `tldrs` not installed → fall back to static tip

---

### Change 4: Smart Hooks — Auto-Inject Extract on Large Reads

**Revised from original "escalating hooks" design** based on ecosystem research:
- Nobody has proven stateful escalating hooks work
- claude-mem proves automatic capture > nagging for cooperation
- Best pattern: pre-compute and hand results to agent for free

**Design principle:** Hooks handle per-file tactical enforcement. Skills handle session-level strategic guidance. The two never duplicate each other.

**Design:**

1. **PostToolUse on Read — files >300 lines:** After a Read completes on a file >300 lines, the hook runs `tldrs extract <file>` and returns the output as `additionalContext`. The agent gets file structure for free — token savings happen whether the agent "chose" tldrs or not.

   > **Why PostToolUse, not PreToolUse:** PreToolUse would block the Read and add latency before the agent sees any content. PostToolUse lets the Read complete normally, then appends extract output alongside it. The agent has both the raw file and the structure summary. On subsequent turns, the structure summary helps the agent avoid re-reading the entire file.
   >
   > **Why 300 lines, not 100:** Files under 300 lines are small enough that the overhead of running extract isn't worth the savings. The sweet spot for extract is files where the agent would otherwise need to re-read to find specific sections. 300 lines is ~6000 tokens raw; extract typically reduces this to ~800 tokens.

2. **PreToolUse on Grep:** Single reminder that `tldrs find` exists for semantic search — same as today, once per session.

3. **No PostToolUse Bash hook.** Detecting `tldrs` commands in Bash output is fragile — agents use `uv run tldrs`, pipe commands, compound commands. Instead, the **CLI itself emits hints** to stderr (see Change 1). The agent sees hints in Bash output naturally.

4. **No escalation state machine.** The briefing (Change 3) + rewritten skills (Change 2) handle strategic adoption. The hook handles tactical "this specific file is big, here's the structure."

**Trade-off:** Running `tldrs extract` inside a PostToolUse hook adds ~1-2s after Read calls on files >300 lines. Acceptable because:
- Only fires on large files (>300 lines)
- The extract output helps the agent target specific sections on subsequent reads
- Net token savings far outweigh the latency cost
- PostToolUse doesn't block the initial Read — agent sees content immediately

---

## Skills Summary

After these changes, the plugin has **6 skills** (same count, all rewritten):

| # | Skill | Trigger | Change |
|---|-------|---------|--------|
| 1 | `tldrs-session-start` | Starting any code task | Rewritten (+ handoff branch) |
| 2 | `tldrs-find-code` | Searching for code | Rewritten |
| 3 | `tldrs-understand-symbol` | Understanding a function/class, before editing | Rewritten (+ before-edit branch) |
| 4 | `tldrs-explore-file` | Analyzing a file | Rewritten |
| 5 | `tldrs-map-codebase` | Understanding project architecture | Rewritten |
| 6 | `tldrs-ashpool-sync` | Syncing eval coverage | Unchanged |

## Hooks Summary

| Hook | Event | Behavior |
|------|-------|----------|
| Setup | Session start | Run `tldrs diff-context --preset compact`, inject output |
| PostToolUse Read | Read of file >300 lines | Run `tldrs extract <file>`, inject output |
| PreToolUse Grep | Any Grep call | Once-per-session reminder about `tldrs find` |

## Implementation Order

1. **Flag presets** (CLI change) — foundation, all other changes reference presets
2. **Skill rewrite** (plugin change) — highest leverage for adoption
3. **Setup hook** (plugin change) — sets session strategy
4. **PostToolUse Read hook** (plugin change) — per-file tactical enforcement

## Design Decisions (Resolved)

These questions from the draft were resolved during flux-drive review:

| Question | Decision | Rationale |
|----------|----------|-----------|
| Should `--preset compact` be default? | No, always explicit | Explicit is predictable; CLI self-hints nudge toward presets |
| Read hook: sync or async? | PostToolUse (after Read completes) | Doesn't block Read; agent gets both raw and structure |
| Read hook timeout? | PostToolUse has 10s timeout; extract takes 1-2s | Plenty of room |
| Presets configurable per-project? | Not in v1 | YAGNI; add `.tldrs/config.toml` support later if needed |
| `session-id auto` source? | Claude Code's `$CLAUDE_SESSION_ID` if available, else CWD+HEAD hash | Session ID is stable across turns, avoids collision |
| Separate `before-edit` skill? | No, folded into `understand-symbol` | One skill per concern, not per trigger moment |
| Separate `handoff` skill? | No, folded into `session-start` | Subagent handoff is a session-start decision |
| PostToolUse Bash hook? | No, CLI self-hints instead | Bash command parsing is fragile; hints in stderr work universally |
| Skills duplicate hook rules? | No — hooks for tactics, skills for strategy | Single enforcement point per behavior; see best-practices doc |

## Open Questions (Remaining)

1. Should the PostToolUse Read hook respect a flag file (fire once per file) or fire on every Read of files >300 lines?
2. Should `tldrs extract` output in the PostToolUse hook be truncated to a token budget (e.g., 500 tokens) to avoid inflating context?
