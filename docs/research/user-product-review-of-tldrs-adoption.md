# User & Product Review: Making Claude Code Reliably Use tldrs

**Date:** 2026-02-13
**Primary User:** Plugin author (power user) + future marketplace adopters
**Job to be Done:** Claude Code should automatically gather token-efficient context before editing code, reducing token consumption by 48-85% while maintaining accuracy.

---

## Executive Summary

This is fundamentally a **product adoption problem** disguised as a technical configuration challenge. The user wants a "recon-first" workflow where Claude Code automatically uses tldrs reconnaissance tools before touching code. However, the real question isn't "how do we force this" but "what user outcome are we optimizing for?"

**Key Finding:** The current 4-layer architecture (CLI presets + MCP server + skills + hooks) already provides the right technical foundation. The adoption gap exists because we're solving for the wrong metric. Instead of "Claude must always run tldrs," optimize for "Claude produces better code with fewer tokens and fewer errors."

**Recommendation:** Direction 2 (CLAUDE.md behavioral rules) + existing MCP server + simplified tool count (12-15 tools max), with a critical shift: make the behavioral rules **outcome-focused** rather than **tool-prescriptive**.

---

## User Profile Analysis

### Who is the Primary User?

**Two distinct user segments with different needs:**

1. **The Author (current, single user):**
   - Power user running 8 Claude Code plugins (interpub, interdoc, tuivision, tool-time, serena, clavain, notion, tldr-swinton)
   - 80+ skills, 100+ tools across all plugins
   - Daily Claude Code usage for development
   - Already has tldrs installed, indexed, and working
   - **Real job:** Ship features faster with fewer token-wasting debugging cycles
   - **Stated want:** Claude must run tldrs before editing
   - **Actual need:** Code changes that work first-time because Claude had the right context

2. **Future Marketplace Adopters (unknown size):**
   - Install plugin via marketplace, may or may not have semantic index built
   - Unknown plugin count, skill density, or familiarity with tldrs concepts
   - **Job:** Get value from the plugin within first session without reading docs
   - **Adoption barrier:** 24 MCP tools + 6 commands + 3 skills = cognitive overload
   - **Success signal:** "That was helpful" feeling when Claude shows them relevant context they didn't know to ask for

---

## Evidence Quality Assessment

### What We Know (Data-Backed)

- **Plugin is installed and functional:** 8 plugins, MCP server runs, hooks fire
- **Current architecture exists:** 24 MCP tools, 3 orchestration skills, 2 hooks (PostToolUse:Read + PreToolUse:Serena), Setup hook
- **Historical adoption research complete:** Three solution docs from 2026-02-11 analyze the adoption problem:
  - `cli-plugin-low-agent-adoption-vs-mcp-20260211.md`: CLI+hooks failed, MCP server built
  - `layered-enforcement-architecture-plugin-20260211.md`: 4-layer defense-in-depth pattern
  - `hooks-vs-skills-separation-plugin-20260211.md`: Hooks for tactics, skills for strategy

- **MCP server shipped:** Commit c8bbd8a (2026-01-23+) implemented MCP response cleanup
- **Plugin streamlining in progress:** Skills retired (find-code, explore-file, understand-symbol) replaced by MCP tools
- **Token savings validated:** 48-85% savings figure cited (diff-context vs raw Read)

### What We're Assuming (Needs Validation)

- **Assumption 1:** "Claude almost never uses tldrs tools"
  - **Evidence needed:** Session logs showing tool call frequency (Read vs tldrs_extract vs tldrs_context)
  - **Validation:** Hook logs from PostToolUse:Read show how often it fires (= how often Claude reads large files)
  - **Counterevidence:** If setup hook shows "151 Python files, 3 changed", and tldrs-session-start skill exists, Claude *should* be triggering it for coding tasks

- **Assumption 2:** "Forcing tldrs via hooks is bad UX due to 3-8s latency"
  - **Evidence needed:** Actual timing data for tldrs operations in this project
  - **Missing context:** Is the bottleneck index build, daemon startup, or analysis time?
  - **Test:** Run `time tldrs diff-context --project . --preset compact` on a clean session

- **Assumption 3:** "CLAUDE.md rules are ineffective because Claude skips them"
  - **Counterevidence:** The tldrs-session-start skill has a broad trigger pattern ("fix bugs, debug, implement features, refactor, write tests, review code, migrate, port, or explore a codebase"). If Claude isn't invoking it, either:
    - The skill isn't loading (plugin version drift? — known issue from memory)
    - The trigger pattern is too narrow
    - Claude is correctly skipping it for tasks where tldrs adds no value (config edits, README updates)

- **Assumption 4:** "24 MCP tools is too many"
  - **Needs segmentation:** How many tools do users need for 80% of value?
  - **Hypothesis:** 5-6 core tools (extract, context, diff-context, find, structural, impact) cover most workflows

### Critical Unknowns

1. **What is the actual tool usage distribution?**
   - Which MCP tools get called in real sessions?
   - Which skills get triggered?
   - Which hooks fire and produce useful output?

2. **What user segment are we optimizing for?**
   - Author's power-user workflow (80+ skills, needs everything)?
   - New marketplace adopters (need simplicity first, power later)?

3. **What does "reliably use tldrs" mean as a measurable outcome?**
   - 100% of coding tasks start with tldrs (tool-prescriptive)?
   - OR: 95% of edits succeed first-try because Claude had the right context (outcome-focused)?

---

## Flow Analysis: Current User Journey

### Entry Point 1: New Coding Session (Author)

**Happy Path:**
1. User starts Claude Code via `cc` in a project directory
2. Setup hook fires → shows project stats + structure output
3. User says "fix the auth bug in login.py"
4. **Decision point:** Does Claude trigger `tldrs-session-start` skill?
   - **IF YES:** Skill guides Claude to run `tldrs diff-context --preset compact`
   - **IF NO:** Claude jumps to `Read login.py` → PostToolUse:Read hook fires → inject `tldrs extract` output as additionalContext

**Current Failure Mode:**
- If skill doesn't trigger AND file is <300 lines, PostToolUse:Read hook skips it → Claude gets raw file only
- If user's request is vague ("something's broken"), Claude may read 5+ files before finding the bug → PostToolUse hook fires 5 times, each showing structure but not *relationships*

**Missing Flow:**
- No "Claude read 3 files in 2 minutes without finding the issue" → escalate to `tldrs diff-context` suggestion
- No visibility into whether the hook's extract output actually helped Claude

### Entry Point 2: Marketplace Install (Future User)

**Happy Path:**
1. User runs `/plugin install tldr-swinton`
2. Setup hook checks tldrs install → **FAILS** (not installed)
3. Setup hook prints: "tldrs: NOT INSTALLED. Install with: pip install tldr-swinton"
4. User installs tldrs, restarts session
5. Setup hook runs `tldrs prebuild` in background, shows project structure
6. User says "show me what this project does"
7. **Decision point:** Does Claude trigger `tldrs-map-codebase` skill?

**Actual Failure Mode (Probable):**
1. User installs plugin
2. Setup hook fails (tldrs not installed)
3. User doesn't see the error message (compressed into setup output)
4. User says "find the authentication logic"
5. Claude tries to call `mcp__plugin_tldr-swinton_tldr-code__find` tool
6. **Tool call fails** because tldrs CLI isn't installed
7. User concludes "plugin is broken" and uninstalls

**Critical UX Gap:**
- No graceful degradation when tldrs isn't installed
- No onboarding flow that validates setup before allowing tool calls
- No "first-run" experience that demonstrates value

### Entry Point 3: Multi-Turn Coding Task (Author)

**Happy Path:**
1. Claude runs `tldrs diff-context --project . --preset compact --session-id auto`
2. Makes an edit, user requests a follow-up change
3. Claude runs `tldrs diff-context` again with same session-id → gets delta markers
4. Token savings compound across 5+ turns

**Actual Flow (Unknown):**
- Does Claude remember to use `--session-id auto` across turns?
- Does the skill's "multi-turn task" detection work, or does Claude need explicit "this is a multi-turn task" from the user?

---

## Direction Evaluation

### Direction 1: Aggressive Hooks (Force tldrs Before Every Edit/Write/Read)

**UX Impact:**
- **Latency:** +3-8 seconds per file operation (assumed, needs measurement)
- **Relevance:** Hook can't know if tldrs output is useful for the task
  - Example: User edits `.gitignore` → hook runs `tldrs extract .gitignore` → wasted 3 seconds, zero value
  - Example: Claude reads `config.json` → hook runs extract → no code structure to extract
- **User Control:** Zero. Hook fires unconditionally.

**Context Impact:**
- Inject analysis the agent didn't request → possible context pollution
- Agent must filter "was this helpful?" signal from noise
- Multi-file tasks: Hook fires 10 times in 60 seconds → 30-80 seconds added latency

**Adoption Impact:**
- New users get slow performance before seeing value
- Power users (the author) get latency on config edits, README updates, etc.

**Verdict:** ❌ **Do Not Adopt.** Violates "first, do no harm." Adds friction to workflows where tldrs provides zero value. No escape hatch.

---

### Direction 2: CLAUDE.md Behavioral Rules ("You MUST run tldrs before editing")

**UX Impact:**
- **Latency:** Only when Claude chooses to run tldrs (task-dependent)
- **Relevance:** Claude's judgment determines when tldrs is useful
  - Skill trigger: "fix bugs, debug, implement features, refactor, write tests, review code, migrate, port, explore codebase"
  - Human-like reasoning: Skip tldrs for "add a comment to this function" (Claude already has the context)
- **User Control:** Claude acts as intelligent filter. User can override: "just read the file directly."

**Context Impact:**
- Task-aware: Diff-context for bug fixes, structure for exploration, context for symbol analysis
- Progressive disclosure: Start with cheap operations (structure), escalate to expensive (semantic search) only if needed

**Adoption Impact:**
- New users: Skill triggers naturally on first coding task → "oh, this shows me what changed" → value demonstration
- Power users: No forced latency on non-coding tasks

**Current Implementation Status:**
- ✅ Skills exist: `tldrs-session-start`, `tldrs-map-codebase`, `tldrs-ashpool-sync`
- ✅ Trigger patterns are broad: "fix bugs, debug, implement features, refactor, write tests..."
- ❓ Unknown: Are skills actually triggering in real sessions?

**Critical Success Factor:** Skill trigger reliability. If Claude doesn't invoke skills, this entire direction fails.

**Verdict:** ✅ **Adopt with measurement.** Requires instrumentation to validate skills are triggering. Add telemetry to skills (write to `/tmp/tldrs-skill-triggered-{session_id}-{skill_name}` flag file) to verify.

---

### Direction 3: Hybrid (Rules + Hooks)

**UX Impact:**
- **Risk:** Double analysis
  - Skill guides Claude to run `tldrs diff-context`
  - Then Claude reads a file → hook also runs `tldrs extract`
  - Result: Two tldrs operations when one would suffice
- **Complexity:** User (and Claude) must understand what's automatic vs manual

**Separation of Concerns (From Existing Architecture):**
- **Hooks:** Per-file tactics (PostToolUse:Read → extract for files >300 lines)
- **Skills:** Session strategy (start with diff-context OR structure based on git status)
- **Overlap Risk:** If skill says "run extract before Read" AND hook auto-runs extract, they conflict

**Current Implementation (From Memory.md):**
- Skills do NOT contain per-file rules like "Never Read >100 lines without extract"
- Hooks handle per-file tactics automatically
- **Clean separation already exists**

**Verdict:** ⚠️ **Already implemented correctly.** The current architecture IS hybrid, but with proper separation. No action needed beyond validating it works.

---

### Direction 4: Simplify Tools (31 → 5-6 Essential)

**Current Tool Count:**
- 24 MCP tools (listed above)
- 6 slash commands (`/tldrs-find`, `/tldrs-diff`, `/tldrs-context`, `/tldrs-structural`, `/tldrs-quickstart`, `/tldrs-extract`)
- 3 skills (session-start, map-codebase, ashpool-sync)

**80/20 Analysis — Which Tools Deliver Most Value?**

**Tier 1: Core Recon (5 tools — must-have):**
1. `extract` — File structure, 85% smaller than raw Read
2. `diff_context` — Token-efficient context for changes (48-73% savings)
3. `context` — Call graph around a symbol
4. `find` (semantic search) — Concept-level search
5. `structure` — Directory-level overview

**Tier 2: Specialized (5 tools — high-value for specific workflows):**
6. `impact` — Show callers before renaming/editing (PreToolUse:Serena hook uses this)
7. `structural_search` — AST-grep for pattern matching
8. `change_impact` — Affected tests detection
9. `distill` — Compress context for sub-agent handoff
10. `tree` — Lightweight file listing

**Tier 3: Deep Analysis (6 tools — niche, power users only):**
11. `cfg` — Control flow graph
12. `dfg` — Data flow graph
13. `slice` — Program slicing
14. `dead` — Dead code detection
15. `diagnostics` — Code quality checks
16. `hotspots` — Complexity hotspots

**Tier 4: Meta/Utility (8 tools — support, not primary):**
17. `arch` — Architecture overview
18. `calls` — Call graph navigation
19. `imports` — Import analysis
20. `importers` — Reverse import lookup
21. `verify_coherence` — Multi-file diff validation
22. `delegate` — Smart retrieval planning
23. `status` — Index/daemon status
24. `search` — Regex search (likely redundant with Grep tool)

**UX Impact of Simplification:**

**Option A: Hide Tier 3/4 tools from MCP, expose via CLI only**
- Reduces cognitive load: 10 MCP tools instead of 24
- Power users can still access via Bash: `tldrs cfg file.py function`
- **Trade-off:** Discoverability. If Claude never suggests `tldrs slice`, users won't know it exists.

**Option B: Tiered tool descriptions with escalation guidance**
- Keep all 24 tools, but tool descriptions guide agents:
  - `extract`: "ALWAYS use this before Read for code files. 85% token savings."
  - `cfg`: "Advanced analysis for debugging complex control flow. Use only when call graph (context) is insufficient."
- **Trade-off:** Relies on Claude reading and following tool descriptions (same challenge as skills)

**Option C: Progressive disclosure via skills**
- Skills recommend Tier 1 tools only
- Tier 2/3/4 tools available but not proactively suggested
- User or Claude can discover advanced tools when they hit a wall with basics
- **Trade-off:** Requires skills to trigger reliably

**Adoption Impact:**
- **New users:** Benefit most from simplification. 10 tools with clear purposes > 24 tools with overlapping use cases.
- **Power users (author):** Need all 24 eventually, but can tolerate discovering them progressively.

**Verdict:** ✅ **Adopt Option C (Progressive Disclosure).** Keep all 24 MCP tools registered, but skills/commands only mention Tier 1 (5 tools) + selective Tier 2 (impact, structural, change_impact). Tool descriptions include escalation hints: "If context doesn't show enough detail, try cfg for control flow."

---

## The Fundamental Question: Tool Usage vs Code Quality Outcomes

### Current Framing (Tool-Prescriptive):

**Goal:** "Claude must run tldrs before editing code"
**Metric:** % of coding sessions where tldrs is invoked
**Success:** 100% of sessions start with `tldrs diff-context`

**Problem with this framing:**
- Optimizes for tool usage, not user outcomes
- No consideration for tasks where tldrs adds zero value (config edits, comment additions, README updates)
- Treats tldrs as mandatory ceremony rather than value-adding recon

### Alternative Framing (Outcome-Focused):

**Goal:** "Claude produces correct code changes with fewer tokens and fewer debugging cycles"
**Metrics:**
- % of edits that compile/pass tests first-try (proxy: no follow-up "fix the error" prompts)
- Token consumption per task (raw Read vs tldrs-guided context)
- Time to resolution (including latency from tldrs operations)

**Success:** 80% of coding tasks complete in one LLM turn because Claude had the right context

**Hypothesis:** If this is the true goal, then:
- **tldrs is a means, not the end**
- **CLAUDE.md rules should be outcome-based:** "Before editing unfamiliar code, gather context to understand impact and dependencies" (HOW = tldrs, but rule doesn't mandate the tool)
- **Skills demonstrate value, not compliance:** "Use tldrs diff-context to see what changed since last commit — saves 60% tokens vs reading all modified files"

---

## Recommended Approach (Synthesis)

### Primary Recommendation: Direction 2 + Simplified Tool Count + Outcome-Focused Rules

**Architecture:**
1. **Keep existing 4-layer defense:**
   - Layer 1: CLI presets (compact, minimal, multi-turn) — ✅ exists
   - Layer 2: Skills for session strategy — ✅ exists
   - Layer 3: Hooks for per-file tactics — ✅ exists (PostToolUse:Read)
   - Layer 4: CLI self-hints — ✅ exists (stderr hints for missing --preset)

2. **Simplify MCP tool visibility (Progressive Disclosure):**
   - Skills mention only 8 tools: extract, diff_context, context, find, structure, impact, structural_search, change_impact
   - All 24 tools remain registered and callable
   - Tool descriptions include escalation guidance: "For deeper analysis, use cfg/dfg/slice"

3. **Reframe CLAUDE.md rules to be outcome-focused:**

   **Current (tool-prescriptive):**
   > "BEFORE reading any code files, run tldrs diff-context or tldrs structure."

   **Proposed (outcome-focused):**
   > **Code Context Gathering (Recon-First Workflow)**
   >
   > Before editing unfamiliar code or starting a debugging task:
   > 1. Understand what changed: Use `/tldrs-diff` or invoke `tldrs-session-start` skill for recent changes context (saves 48-73% tokens vs reading raw diffs).
   > 2. Understand impact: If editing/renaming a function, check callers first (the `impact` tool shows this automatically before Serena edits).
   > 3. Find related code: Use `/tldrs-find "concept"` for semantic search instead of grepping.
   >
   > **When to skip recon:**
   > - Editing a file you already read this session
   > - Simple config changes (.json, .yaml, .toml)
   > - Adding comments or docstrings to code you already understand
   >
   > **Goal:** Reduce token waste and debugging cycles by gathering the right context before making changes.

4. **Add skill trigger telemetry:**
   - Each skill writes a flag file: `/tmp/tldrs-skill-triggered-{session_id}-{skill_name}-{timestamp}`
   - Setup hook or slash command to inspect: "Which skills triggered this session?"
   - **Validation:** If skills aren't triggering, investigate skill matcher patterns or add more explicit user-facing commands

5. **Improve first-run experience (marketplace adopters):**
   - Setup hook: If tldrs not installed, print error + install command + **return non-zero exit code** so Claude Code shows a clear failure
   - Add `/tldrs-quickstart` as first command mentioned in plugin description
   - Setup hook: If semantic index not built, suggest `tldrs index .` with estimated time ("~30 seconds for 150 Python files")

6. **Measure actual tool usage:**
   - MCP server: Log tool calls to `/tmp/tldrs-mcp-calls-{session_id}.jsonl`
   - Format: `{"timestamp": "...", "tool": "extract", "args": {...}, "duration_ms": 234}`
   - Weekly review: Which tools are used? Which are never called?

---

## Adoption Risks & Mitigation

### Risk 1: Skills Don't Trigger Reliably

**Symptom:** User reports "Claude never uses tldrs even though plugin is installed"
**Root Causes:**
- Skill trigger patterns too narrow
- Claude's skill matcher doesn't recognize the task pattern
- Plugin version drift (known issue from memory) → skills not loading

**Mitigation:**
- Add telemetry (flag files) to verify skill triggers
- Widen trigger patterns in SKILL.md
- Add explicit user-facing commands as fallback: `/tldrs-diff`, `/tldrs-context foo`

### Risk 2: New Users Skip Setup (tldrs Not Installed)

**Symptom:** User installs plugin, MCP tools fail, user uninstalls
**Root Causes:**
- Setup hook error message buried in output
- No forcing function to complete setup before using tools

**Mitigation:**
- Setup hook: Return non-zero exit code if tldrs not installed (makes error visible in Claude Code UI)
- MCP tools: Detect missing tldrs, return helpful error: "tldrs CLI not installed. Run: pip install tldr-swinton"
- Plugin description: Add installation instructions as first section

### Risk 3: Tool Count Overwhelms New Users

**Symptom:** User sees 24 MCP tools in palette, doesn't know where to start
**Root Causes:**
- No clear "start here" guidance
- All tools have equal visibility

**Mitigation:**
- Progressive disclosure: Skills mention only 8 core tools
- Tool descriptions include "When to use" guidance
- `/tldrs-quickstart` command as entry point

### Risk 4: Latency from tldrs Operations Exceeds User Patience

**Symptom:** User says "this is too slow" after tldrs operations take 5+ seconds
**Root Causes:**
- Daemon not running (startup overhead)
- Semantic index not built (falls back to slower tree-sitter-only analysis)
- Network-mounted project directory (I/O latency)

**Mitigation:**
- Setup hook prebuild: `tldrs prebuild --project . &` in background
- Tool descriptions include timing expectations: "~200ms with warm daemon, ~2s cold start"
- Preset defaults: `budget=4000` prevents unbounded output size

---

## Success Metrics (Measurable Outcomes)

### For the Author (Power User)

**Primary Metric:** Token consumption per coding task
- **Baseline:** Average tokens consumed for "fix bug in X" task using raw Read
- **Target:** 50% reduction when tldrs provides context

**Secondary Metrics:**
- % of edits that compile/pass tests first-try (proxy: no "fix the error" follow-ups within 3 turns)
- Time to resolution (including tldrs latency)

**Instrumentation:**
- MCP call logs: `/tmp/tldrs-mcp-calls-{session_id}.jsonl`
- Session outcome journal: "Task description | tldrs used? | tokens | turns to completion | success?"

### For Marketplace Adopters (Future Users)

**Primary Metric:** % of users who complete first coding task successfully within first session
- **Target:** 70%+ of users see value in session 1

**Secondary Metrics:**
- Plugin retention: % still installed after 7 days
- Skill trigger rate: % of coding sessions where `tldrs-session-start` fires

**Instrumentation (Privacy-Preserving):**
- Setup hook: Write `/tmp/tldrs-first-run-{timestamp}` flag on first session
- Skill triggers: Count flag files in `/tmp/tldrs-skill-triggered-*`
- No PII, no phone-home telemetry — local logs only

---

## Open Questions for User Research

### Question 1: What Does "Reliably Use tldrs" Mean?

**Ask the user:**
- "When you say Claude should 'reliably use tldrs,' do you mean:
  - (A) Claude runs tldrs on 100% of coding tasks, even simple ones?
  - (B) Claude runs tldrs when it would improve outcomes (fewer errors, fewer tokens)?
  - (C) Claude never makes a code edit without understanding impact and context (tldrs is one way to achieve this)?"

**Why it matters:** Answer determines whether we optimize for tool usage compliance or code quality outcomes.

### Question 2: Which Use Cases Matter Most?

**Ask the user:**
- "Rank these scenarios by importance:
  1. Fix a bug in unfamiliar code (high value for tldrs diff-context + impact analysis)
  2. Add a new feature across multiple files (high value for structure + context)
  3. Refactor a function (high value for impact to check callers)
  4. Update a README (zero value for tldrs)
  5. Add a comment to a function (zero value for tldrs)"

**Why it matters:** If 80% of tasks are scenarios 1-3, aggressive tldrs enforcement makes sense. If 50% are scenarios 4-5, forced hooks create friction.

### Question 3: Are You Optimizing for Your Workflow or Marketplace Adoption?

**Ask the user:**
- "Is the goal:
  - (A) Make tldrs work perfectly for your own daily workflow (power user, 80+ skills, knows all tools)?
  - (B) Make tldrs easy for new marketplace users to adopt (simplicity, quick wins, gradual learning curve)?
  - (C) Both, but willing to accept different defaults/modes for each segment?"

**Why it matters:** Power users tolerate complexity and latency for power. New users need instant value with minimal setup. These may require different presets or modes.

### Question 4: What's an Acceptable Latency Trade-Off?

**Ask the user:**
- "For a 'fix this bug' task, which would you prefer:
  - (A) 3 seconds for tldrs diff-context upfront, then Claude edits correctly first-try (total: 3s + 10s = 13s)
  - (B) 0 seconds upfront, Claude reads raw file and makes a wrong guess, you correct, Claude fixes it (total: 0s + 10s + 15s + 12s = 37s)
  - (C) Depends on the task — Claude should judge when recon is worth the latency"

**Why it matters:** Validates whether latency concerns are about absolute time or wasted time from wrong-path edits.

---

## Conclusion

The adoption problem for tldrs is not primarily technical — the 4-layer architecture (presets + MCP + skills + hooks) already provides the right enforcement mechanisms. The real challenge is **aligning the enforcement strategy with measurable user outcomes.**

**Core Insight:** "Claude must always run tldrs" optimizes for tool compliance. "Claude produces correct code with fewer tokens and errors" optimizes for user value. These point to different solutions.

**Recommended Path:**
1. **Keep Direction 2 (CLAUDE.md rules + skills)** with outcome-focused language
2. **Simplify tool visibility** to 8 core tools in skills, 24 total available
3. **Measure skill trigger rates** to validate skills are firing
4. **Instrument token savings** to validate value hypothesis
5. **Improve first-run setup** for marketplace adopters

**Next Action:** Ask the user the 4 open questions to validate assumptions before implementing changes. The answers will determine whether to tighten enforcement (more aggressive hooks) or improve value demonstration (better skill triggers + tool descriptions).

---

## Appendix: Flow Diagrams

### Current Flow (Inferred)

```
User: "Fix the bug in auth.py"
  ↓
Claude: Check skill triggers
  ↓
IF skill "tldrs-session-start" matches:
  ↓
  Skill loads → guides Claude to run `tldrs diff-context --preset compact`
  ↓
  Claude runs tldrs, gets context, reads auth.py, makes edit
ELSE:
  ↓
  Claude runs Read(auth.py)
  ↓
  PostToolUse:Read hook fires
  ↓
  IF file >300 lines: inject tldrs extract output
  ↓
  Claude uses raw file + extract structure, makes edit
```

### Proposed Flow (Outcome-Focused)

```
User: "Fix the bug in auth.py"
  ↓
Claude: Assess task (is this familiar code? recent changes? simple fix?)
  ↓
IF unfamiliar OR multi-file OR complex:
  ↓
  Trigger tldrs-session-start skill OR invoke /tldrs-diff command
  ↓
  Get diff-context, understand what changed, make informed edit
ELSE IF familiar + simple:
  ↓
  Read file directly (PostToolUse hook still provides structure if >300 lines)
  ↓
  Make edit
```

Key difference: Claude's judgment determines when recon adds value, rather than enforcing recon unconditionally.
