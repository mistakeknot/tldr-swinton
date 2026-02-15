# Architecture Review: Enforcing tldrs Reconnaissance in Claude Code

**Date**: 2026-02-13
**Reviewer**: Claude Opus 4.6
**Context**: Evaluating 4 architectural approaches to ensure Claude Code invokes tldrs tools before code manipulation

---

## Executive Summary

**Recommendation**: Direction 5 (new) — **Behavioral Rules + Quality-of-Life Automation**

The current problem is NOT architectural. It's a **mismatch between enforcement mechanism and platform capabilities**. Claude Code has no "BeforeFirstToolCall" hook, and skills are suggestions among 80+ competing skills. The real issue: **tldrs is positioned as mandatory infrastructure but built as optional enhancement**.

The solution: Accept that Claude Code won't reliably auto-invoke tools, and instead make tldrs **so frictionless that explicit invocation is the path of least resistance**.

**Key finding**: 24 MCP tools, 3 skills, 3 hooks, 6 slash commands = 36 touch points. This is not tool selection paralysis — it's **unclear value proposition**. Developers don't know when to use which tool.

---

## Current State Analysis

### Plugin Surface Inventory

**MCP Tools** (24 tools, `tldr-code` server):
- Navigation: `tree`, `structure`, `search`, `extract`
- Context (flagship): `context`, `diff_context`, `delegate`, `distill`
- Flow analysis: `cfg`, `dfg`, `slice`
- Codebase: `impact`, `dead`, `arch`, `calls`
- Imports: `imports`, `importers`
- Semantic: `semantic`
- Quality: `diagnostics`, `change_impact`, `verify_coherence`
- Structural: `structural_search`
- Attention: `hotspots`
- Admin: `status`

**Skills** (3 orchestration skills):
- `tldrs-session-start`: "BEFORE reading any code files" (lines 10, 45, 65)
- `tldrs-map-codebase`: Explore unfamiliar projects
- `tldrs-ashpool-sync`: Internal tool sync

**Hooks** (3 hooks):
- Setup: Session start briefing + prebuild cache
- PreToolUse:Serena (2 matchers): Auto-inject caller analysis before edits/renames
- PostToolUse:Read: Auto-inject `extract --compact` for files >300 lines

**Slash Commands** (6 commands):
- `/tldrs-find`, `/tldrs-diff`, `/tldrs-context`, `/tldrs-structural`, `/tldrs-quickstart`, `/tldrs-extract`

**Total touch points**: 36 entry points (24 + 3 + 3 + 6)

### Evidence of Non-Adoption

1. **Zero organic hook fires**: All `/tmp/tldrs-*` flag files are from manual testing (dates: Feb 9-12, owner: root/claude-user test sessions)
2. **PostToolUse:Read never triggered**: Zero `/tmp/tldrs-extract-*` files despite many coding sessions
3. **Skills ignored**: Session transcripts show Claude reads files directly without invoking `tldrs-session-start`
4. **MCP server healthy**: 17+ processes running correctly, server starts fine — but tools not called

**Root cause hypothesis**: Claude Code's tool selection algorithm sees:
- 100+ total tools (Read, Grep, Glob, Edit, Bash, Serena, Notion, MCP servers)
- tldrs as 24 more options, not as required pre-flight
- Skills as suggestions, not mandates

---

## Direction-by-Direction Analysis

### Direction 1: Expand PreToolUse Hooks Aggressively

**Proposal**: Add PreToolUse matchers for Edit, Write, Bash (any code manipulation). Auto-run `tldrs context` or `diff-context` before Claude touches code.

#### Boundaries & Coupling Analysis

**Pros**:
- Guarantees execution — hooks are enforced by platform
- No reliance on model cooperation or skill visibility
- Consistent recon regardless of task framing

**Cons — Architecture Violations**:
1. **Stateless hooks can't understand intent**: A PreToolUse:Edit hook sees `file_path` but not "why" Claude is editing. Can't distinguish between:
   - Fixing a typo in a comment (no recon needed)
   - Refactoring a critical function (recon essential)
   - Editing a config file (no Python analysis needed)
2. **Context pollution at scale**: Every Edit/Write/Bash call triggers tldrs, injecting context Claude didn't request and may not need. This creates noise, not signal.
3. **Latency penalty on every operation**: 8-10 second hook timeout applied to operations that should be instant (e.g., `echo "foo" > file.txt`). Degrades UX for marginal safety.
4. **Hidden cross-file coupling**: Hooks fire independently per tool call. No shared state to prevent duplicate analysis across a multi-file edit sequence.
5. **Fighting the platform**: PreToolUse hooks are designed for **validation** (e.g., "don't edit files outside workspace"), not **preprocessing** (e.g., "run analysis before every edit").

**Complexity Risk**: Each new matcher (Edit, Write, Bash) introduces 3 failure modes:
- Hook timeout (kills the edit attempt)
- tldrs daemon down (hook returns empty, edit proceeds blind)
- Duplicate injection (multiple hooks fire for compound operations like "Write then Bash")

**Pattern Assessment**: This is an **anti-pattern** — using hooks as a workaround for missing "BeforeFirstToolCall" capability. Hooks are the wrong boundary for task-aware preprocessing.

**Verdict**: Architecturally unsound. Violates separation of concerns (validation vs analysis) and introduces accidental complexity.

---

### Direction 2: CLAUDE.md Behavioral Rules

**Proposal**: Add explicit rules to CLAUDE.md: "BEFORE editing any file, you MUST run tldrs context <function>" or "Always run /tldrs-diff before starting a coding task."

#### Boundaries & Coupling Analysis

**Pros**:
- Respects Claude's autonomy and task awareness
- No latency penalty — tldrs runs only when relevant
- Selective invocation based on context (user's ask + file type + project state)
- Leverages existing CLAUDE.md authority (highest-priority instructions)

**Cons**:
1. **Skills already tried instruction-based enforcement and failed**: `tldrs-session-start` skill line 10: "BEFORE reading any code files, determine your starting point." This is a SHOULD-level instruction, and Claude ignores it.
2. **Competing with 80+ other skills**: CLAUDE.md is loaded into system prompt alongside all other skills. tldrs rules are diluted by noise.
3. **No feedback loop**: If Claude skips the rule, there's no runtime signal. Hook flags would show violations; CLAUDE.md violations are silent.

**Complexity Risk**: Low. Adding 5-10 lines to CLAUDE.md is trivial. But **effectiveness risk is high** — this has already been tried (via skills) and failed.

**Pattern Assessment**: This is the **correct architectural layer** (task-aware, instruction-driven) but **insufficient enforcement mechanism** (no runtime validation). It's fighting model behavior, not platform limitations.

**Verdict**: Architecturally sound but empirically ineffective. Without runtime enforcement, rules get ignored under token pressure or competing priorities.

---

### Direction 3: Hybrid — CLAUDE.md + PreToolUse Enforcement

**Proposal**: Combine Direction 1 and 2. CLAUDE.md says "use tldrs before editing", and PreToolUse hooks enforce it as a safety net.

#### Boundaries & Coupling Analysis

**Pros**:
- Defense in depth: instructions guide behavior, hooks catch violations
- Addresses both "Claude forgets" and "Claude ignores" failure modes

**Cons — Complexity Explosion**:
1. **Duplicate analysis**: Claude runs `tldrs context foo`, then hook fires on Edit and runs it again. Now we have 2x the context, 2x the tokens, 2x the latency.
2. **Inconsistent state**: CLAUDE.md instructs `diff-context`, hook injects `context <symbol>`. Which context is authoritative?
3. **Debugging nightmare**: When tldrs output appears in the conversation, did it come from:
   - Explicit user `/tldrs-*` command?
   - Claude following CLAUDE.md rule?
   - Hook auto-injection?
   - Setup hook at session start?
4. **Architectural entropy**: Two enforcement layers means two points of failure, two config surfaces (CLAUDE.md text + hooks.json matchers), and no single source of truth for "when to run tldrs."

**Complexity Risk**: High. Every change to "when to use tldrs" requires updates to both CLAUDE.md prose and hook matchers. Over time, they drift and contradict.

**Pattern Assessment**: **God-module smell**. This centralizes all "ensure tldrs runs" logic into an omnipresent enforcement layer that touches every tool call. Creates tight coupling between tldrs and the entire tool surface.

**Verdict**: Architecturally unsound due to duplication and tight coupling. Fighting both platform limitations (no BeforeFirstToolCall hook) and model behavior (ignores skills). The complexity is worse than either Direction 1 or 2 alone.

---

### Direction 4: Simplify to 5-6 MCP Tools with Excellent Descriptions

**Proposal**: Reduce from 24 tools to 5-6 core essentials (e.g., `diff_context`, `context`, `find`, `extract`, `structural_search`, `verify_coherence`). Trust Claude's tool selection with better descriptions.

#### Boundaries & Coupling Analysis

**Pros**:
- Reduces tool selection paralysis: 6 tools instead of 24 = clearer decision surface
- Leverages Claude's natural tool selection (proven to work for Read, Grep, Edit)
- Lower maintenance burden: fewer tool descriptions to keep fresh

**Cons**:
1. **Still optional**: Even with 6 tools and perfect descriptions, Claude can choose Read+Grep instead. No enforcement mechanism.
2. **Loses specialized capabilities**: Cutting `cfg`, `dfg`, `slice`, `impact`, `arch`, `dead`, etc. sacrifices tldrs's unique value (flow analysis, reverse call graph).
3. **Description quality doesn't solve visibility**: Current MCP tool descriptions are already detailed (see `context` tool: 30 lines, explains presets, delta mode, token savings). Claude still doesn't invoke them.
4. **Assumes wrong problem**: The issue isn't "too many tools confuse Claude." The issue is "Claude doesn't recognize when tldrs is necessary." Reducing tools doesn't change that.

**Complexity Risk**: Low (fewer tools = simpler). But **effectiveness risk is unchanged** — we still rely on optional tool selection.

**Pattern Assessment**: This is **premature optimization**. The hypothesis "24 tools cause paralysis" is unproven. Evidence shows Claude happily navigates 100+ tools (all MCP servers + built-ins). The real problem is **value proposition**, not tool count.

**Simplicity Violation**: Collapsing 24 tools into 6 would force users to learn a smaller API surface, but **hides tldrs's differentiators**. For example, merging `impact` (reverse call graph) into `context` makes it invisible unless you read the docs.

**Verdict**: Architecturally neutral (no major coupling changes) but strategically misguided. Solves a hypothetical problem (too many tools) while ignoring the real problem (unclear when to use tldrs).

---

## Direction 5: Behavioral Rules + Quality-of-Life Automation (NEW)

**Proposal**: Accept that Claude Code won't auto-invoke tools reliably. Instead, make tldrs **so frictionless that manual invocation is faster than not using it**. Combine:

1. **CLAUDE.md rules** (task-aware guidance, not mandates): "When fixing a bug, start with `/tldrs-diff`. When exploring a new file, start with `/tldrs-extract <file>`."
2. **Slash commands as primary interface** (not MCP tools): `/tldrs-diff`, `/tldrs-context <symbol>`, `/tldrs-extract <file>`. Users type these explicitly.
3. **PostToolUse hooks for ergonomics** (not enforcement): Keep PostToolUse:Read for files >300 lines. Add value without blocking.
4. **Remove PreToolUse hooks** (fighting the platform): Delete PreToolUse:Serena. If Serena edits break callers, that's a verification problem, not a pre-flight problem. Use `verify_coherence` post-edit instead.
5. **Skill simplification**: Collapse `tldrs-session-start` into a **one-line nudge** in Setup hook: "Tip: Run `/tldrs-diff` before editing to see recent changes." Remove "BEFORE reading" imperatives (they don't work).

### Architecture Justification

#### Boundaries & Coupling

**Separation of concerns**:
- **User intent layer** (slash commands): Explicit, discoverable, task-aligned. Users invoke `/tldrs-diff` when they want diff context.
- **Ergonomic automation layer** (PostToolUse:Read): Fires after Read, adds value without blocking. Claude can ignore it (it's `additionalContext`).
- **Guidance layer** (CLAUDE.md + Setup hook): Lightweight suggestions, not enforcement. No runtime coupling.

**Dependency direction**: One-way. Slash commands call tldrs CLI → tldrs daemon → MCP tools (optional). No reverse dependencies (MCP tools don't know about slash commands).

**Ownership boundaries**: Clear. Slash commands own UX. MCP tools own API contracts. Hooks own ergonomics. No overlap.

#### Pattern Analysis

**Design pattern**: **Nudge architecture**. Make the right thing easy, not mandatory.

**Anti-patterns avoided**:
- No god-module enforcement layer (Direction 3)
- No stateless hooks with cross-cutting concerns (Direction 1)
- No premature API reduction (Direction 4)
- No reliance on ignored skill instructions (Direction 2)

**Cohesion**: Each component has a single responsibility:
- Slash commands: user-facing task completion
- MCP tools: programmatic API for other tools (e.g., Serena calling `impact` before edits)
- Hooks: background enhancements (extract large files post-Read)
- Skills: removed (replaced by Setup hook tip)

#### Simplicity & YAGNI

**What we delete**:
- PreToolUse:Serena hooks (2 matchers) — fighting the platform, brittle
- `tldrs-session-start` skill (76 lines) — ignored by Claude, creates false expectation of auto-invoke
- `tldrs-map-codebase` skill — redundant with `/tldrs-quickstart` command
- "BEFORE reading" imperatives in docs — replace with "When you need X, use Y"

**What we keep**:
- PostToolUse:Read hook — adds value, doesn't block, fires conditionally (>300 lines)
- Setup hook — lightweight tip, no enforcement
- 24 MCP tools — API surface for programmatic access (other plugins, future LLM tool-use improvements)
- 6 slash commands — primary UX

**What we add**:
- **Tab completion for slash commands** (if possible in Claude Code plugin API)
- **Usage examples in Setup hook output**: "Tip: `/tldrs-diff` (recent changes), `/tldrs-context <func>` (call graph)"
- **Error messages that teach**: When tldrs fails, suggest the right command. E.g., "No symbol 'foo' found. Run `/tldrs-extract file.py` to see available symbols."

#### Coupling Risk Mitigation

**Before (Direction 3 — hybrid enforcement)**:
- CLAUDE.md prose coupled to PreToolUse hook matchers (must stay in sync)
- Hook logic duplicates skill logic (both decide when to run tldrs)
- Edit/Write/Bash tools coupled to tldrs (can't modify files without triggering hooks)

**After (Direction 5 — nudge architecture)**:
- CLAUDE.md prose decoupled from runtime (suggestions, not contracts)
- No duplication (hooks add value, don't enforce)
- Edit/Write/Bash tools independent of tldrs (hooks only on Read, and only for ergonomics)

---

## Fundamental Tensions Resolved

### 1. Hooks are stateless/context-free vs skills are stateful/context-aware but optional

**Direction 5 resolution**: Stop trying to make stateless hooks context-aware. Use them only for **universal enhancements** (PostToolUse:Read for large files). Context-aware decisions belong in **user-invoked commands** (slash commands), not auto-triggered hooks.

**Example**: Instead of PreToolUse:Edit hook that guesses "should I run `context` or `diff-context`?", the user runs `/tldrs-diff` when they start a task and `/tldrs-context <func>` when they drill into a symbol. The tool adapts to the user's mental model, not the hook's blind heuristic.

### 2. tldrs as mandatory infrastructure vs optional enhancement

**Direction 5 resolution**: **Reframe tldrs as optional but highly incentivized**. It's not a gatekeeper — it's a shortcut.

**Analogy**: `git status` before `git commit`. Not mandatory (you can commit blind), but skipping it is risky. Developers learn to run `git status` because the cost of NOT running it (committing the wrong files) is high. Similarly, `/tldrs-diff` before editing saves time (reading full files) and reduces errors (editing without context).

**How to incentivize without mandating**:
- Show token savings in output: "✓ Saved 1,847 tokens vs reading 3 full files"
- Setup hook tip: "Pro tip: `/tldrs-diff` sees recent changes in 48% fewer tokens"
- Error messages that guide: "Symbol 'foo' not found in diff. Run `/tldrs-context foo` to find callers."

### 3. 24-tool MCP surface — anti-pattern or comprehensive API?

**Direction 5 resolution**: **It's a comprehensive API, not a user-facing menu**. The 24 MCP tools are for:
1. **Programmatic access** (other plugins, future tool-use LLMs)
2. **Internal use** (slash commands and hooks call MCP tools under the hood)
3. **Power users** (direct MCP tool calls for scripting)

**Users interact with 6 slash commands**, not 24 MCP tools. The MCP surface is an **implementation detail**, not the UX.

**Evidence**: Successful projects with large MCP surfaces:
- `mcp-server-filesystem`: 20+ tools (read, write, move, search, etc.)
- `mcp-server-github`: 30+ tools (issues, PRs, repos, commits, etc.)

Large MCP surfaces work when there's a **clear primary UX** (GitHub UI, file manager). tldrs's mistake: exposing MCP tools as primary UX instead of **slash commands as primary, MCP as secondary**.

---

## Recommendations

### Immediate Actions (Week 1)

1. **Delete PreToolUse:Serena hooks** (`pre-serena-edit.sh`, 2 matchers in `hooks.json`)
   - Rationale: Fighting the platform, brittle, zero evidence of value (no real flag files)
   - Replacement: Document in AGENTS.md: "Before renaming a widely-used function, run `/tldrs-context <func>` to see callers"

2. **Simplify Setup hook** to one-line tip:
   ```bash
   echo "Tip: /tldrs-diff (recent changes), /tldrs-context <func> (call graph), /tldrs-extract <file> (structure)"
   ```
   - Remove dynamic `tldrs structure` call (adds latency, rarely useful without user request)
   - Keep prebuild cache background job (fast, valuable)

3. **Retire `tldrs-session-start` and `tldrs-map-codebase` skills**:
   - Replace with Setup hook tip (above)
   - Keep `tldrs-ashpool-sync` (internal tool, different purpose)

4. **Update CLAUDE.md** to remove imperatives:
   - Before: "BEFORE reading any code files, you MUST run tldrs"
   - After: "When fixing bugs or reviewing diffs, `/tldrs-diff` shows changes in 48% fewer tokens than reading full files"

5. **Add usage examples to all 6 slash commands**:
   - Include token savings estimates
   - Show before/after comparisons ("Reading 3 files = 4,200 tokens. `/tldrs-diff` = 1,800 tokens")

### Medium-Term Improvements (Month 1)

6. **Enhance error messages** to guide next steps:
   - "No symbol 'foo' found in call graph. Run `/tldrs-extract src/module.py` to see available symbols."
   - "Diff is empty (no recent changes). Run `/tldrs-context main` to explore from entry point."

7. **Add token usage tracking** to MCP tools:
   - Return metadata: `{"result": "...", "tokens_saved": 1847, "vs_reading_files": ["a.py", "b.py", "c.py"]}`
   - Surface in slash command output

8. **Improve PostToolUse:Read hook**:
   - Add file type detection (skip for .md, .json, .txt)
   - Show symbol count in output: "File contains 12 functions, 3 classes (517 lines)"

9. **Document the MCP → slash command mapping**:
   - Add to AGENTS.md: "MCP tools are for programmatic access. Users should prefer slash commands."
   - Add table: `/tldrs-diff` → `diff_context` MCP tool, etc.

### Long-Term Architecture (Quarter 1)

10. **Evaluate MCP tool consolidation** (Direction 4, but as optimization, not primary fix):
    - Merge rarely-used tools (e.g., `dead`, `arch` → `codebase_analysis` with `--type` param)
    - Keep specialized tools if they have clear use cases (`cfg`, `dfg`, `slice` for debugging)
    - **Do this AFTER measuring tool usage**, not speculatively

11. **Add telemetry** (if privacy-acceptable):
    - Track which slash commands users invoke
    - Track which MCP tools are called (and by whom — user vs hook vs other plugin)
    - Use data to guide UX improvements

12. **Explore Claude Code plugin API enhancements**:
    - Request "BeforeFirstToolCall" hook type (upstream to Anthropic)
    - Request tab-completion for slash commands
    - Request skill prioritization API (mark tldrs skills as "high priority")

---

## Conclusion

**The real problem**: tldrs is positioned as mandatory infrastructure (skills say "BEFORE reading", "MUST run") but architected as optional enhancement (no enforcement mechanism). This creates a **gap between promise and reality**.

**The real solution**: Close the gap by **lowering the promise** (from mandatory to incentivized) and **raising the reality** (from invisible MCP tools to prominent slash commands).

**Why Direction 5 wins**:
1. **Respects platform boundaries**: No stateless hooks pretending to be context-aware
2. **Reduces coupling**: Slash commands independent of Edit/Write/Bash tools
3. **Embraces simplicity**: Delete 100+ lines of skills and hooks, replace with 1-line Setup tip
4. **Aligns with user mental model**: "When I need diff context, I run `/tldrs-diff`" (explicit) vs "Claude should auto-run tldrs before I edit" (implicit, unreliable)
5. **Measurable success criteria**: Track slash command usage, not "did Claude invoke the skill?"

**Why other directions fail**:
- **Direction 1** (hooks everywhere): Fights the platform, introduces latency and noise
- **Direction 2** (CLAUDE.md rules): Already tried via skills, empirically ineffective
- **Direction 3** (hybrid): Worst of both, doubles complexity
- **Direction 4** (reduce tools): Solves wrong problem (tool count ≠ visibility issue)

**Next step**: Implement Immediate Actions (delete PreToolUse hooks, simplify Setup, retire skills, rewrite CLAUDE.md) and measure adoption via slash command usage. If adoption remains low, the problem is **value proposition** (tldrs doesn't save enough time/tokens), not architecture.
