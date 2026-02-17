# Product Review: Intermap Extraction PRD

**Reviewer:** Flux-drive User & Product Reviewer
**Date:** 2026-02-16
**PRD:** `/root/projects/Interverse/docs/prds/2026-02-16-intermap-extraction.md`
**Status:** BLOCK — Critical discoverability and adoption risks

---

## Executive Summary

This PRD proposes extracting project-level analysis tools from tldr-swinton into a new "intermap" plugin. **Primary finding: The split will likely cause significant user confusion and workflow friction** for both Claude Code agents and human developers working across the 27+ plugin ecosystem.

**Three critical issues:**

1. **Tool discoverability crisis** — Agents won't know which plugin owns which analysis capability
2. **Missing migration/transition plan** — No strategy for existing workflows that depend on tldr-swinton tools
3. **Value proposition unclear** — Why agents should install/use intermap is never stated

**Recommendation:** BLOCK until discoverability, migration strategy, and user value are addressed.

---

## Primary User: Claude Code Agents

**Job to be done:** Analyze code architecture and dependencies across a multi-project monorepo to make informed refactoring/feature decisions.

**Current workflow:**
1. Agent receives task: "Add OAuth to the API service"
2. Agent calls tldr-swinton MCP tools: `impact()`, `calls()`, `arch()` to understand dependencies
3. Agent uses results to plan changes and identify affected files
4. Agent proceeds with implementation

**Proposed workflow (post-extraction):**
1. Agent receives same task
2. Agent must somehow know to call **intermap** (not tldr-swinton) for `impact()`, `calls()`, `arch()`
3. Agent calls **tldr-swinton** for `extract()`, `context()`, `structure()`
4. Agent synthesizes results from two different plugins

**Problem:** Step 2 assumes agents have perfect mental models of which plugin owns which capability. Evidence suggests this is false.

---

## UX Review

### Critical Issue #1: Tool Name Collisions Without Disambiguation

**Problem:** Six tools move from tldr-swinton to intermap with **identical names**:
- `arch()`, `calls()`, `dead()`, `impact()`, `change_impact()`, `diagnostics()`

**Agent experience:**
- MCP tool registry shows both `tldr_swinton::impact` and `intermap::impact` (or one replaces the other)
- No naming convention signals which is which
- Agent prompt says "use impact() to see callers" — which one?
- No help text differentiates them

**Evidence gap:** PRD assumes agents will "just know" to call intermap for project-level analysis. No research validates this assumption. No onboarding/discovery mechanism described.

**Failure mode:** Agents call whichever tool loads first, get wrong results or errors, and lose confidence in both plugins.

**Severity:** **HIGH** — Blocks successful task completion

---

### Critical Issue #2: No Migration Path for Existing Workflows

**Affected users:**
- Claude Code agents with session context referencing tldr-swinton tools
- Human developers with muscle memory for `/tldrs-` commands
- Existing skills/hooks/agents that invoke tldr-swinton MCP tools

**Current state (from AGENTS.md):**
```
Available commands:
- /tldrs-find <query>
- /tldrs-diff
- /tldrs-context <symbol>
...

Hooks:
- PreToolUse on Serena: Runs `tldrs impact` before edits
```

**Post-extraction state (PRD claims):**
- Tools removed from tldr-swinton MCP server (F3)
- No replacement commands created
- No hook migration described
- No skill updates specified

**Failure mode:**
- Pre-edit hook calls `tldr_swinton::impact` → tool not found → hook fails → edit proceeds without caller analysis → regression in safety
- Agent tries `/tldrs-arch` → command not found → agent doesn't discover `/intermap:arch` exists
- Session context says "use tldr-swinton for impact analysis" → agent calls removed tool → error → retries → exhausts context window

**Missing from PRD:**
- Deprecation timeline
- Backward-compatibility shims
- Command/skill migration checklist
- User notification plan

**Severity:** **CRITICAL** — Breaks existing production workflows

---

### Critical Issue #3: Value Proposition Never Stated

**What the PRD explains:**
- Technical problem: tldr-swinton is too big (1.4 MB)
- Solution: Split into two plugins
- Implementation details: Go MCP + Python subprocess

**What the PRD never explains:**
- Why should an **agent** care about this split?
- What **new capability** does intermap enable that couldn't exist in tldr-swinton?
- When should an agent **choose intermap over tldr-swinton**?

**Agent decision criteria (missing):**
```
Use tldr-swinton when: [undefined]
Use intermap when: [undefined]
Use both when: [undefined]
```

**Evidence:** F4 (project registry) and F5 (agent overlay) are genuinely new capabilities. But their value is buried in acceptance criteria, not highlighted as user-facing benefits.

**Example of missing messaging:**
> "Intermap lets you see **which agents are editing which projects right now** (via intermux integration), so you can avoid merge conflicts before they happen."

vs. current messaging:
> "F5: Agent Overlay (intermux Integration) — Enrich project map with live agent activity data from intermux."

The first tells agents **why to care**. The second is a technical spec.

**Severity:** **HIGH** — Low adoption even if technically sound

---

## Product Validation

### Problem Definition: Weak Evidence

**Claim:** "tldr-swinton is a 1.4 MB monolith conflating two concerns"

**Challenge:**
- Is 1.4 MB actually a problem? For whom? What breaks?
- Evidence cited: None
- User complaints referenced: None
- Performance data: None

**What would validate this:**
- "tldr-swinton takes 8+ seconds to cold-start its daemon, blocking agent workflows" (measurable)
- "Agents report confusion when calling `impact()` on a single file vs. whole project" (user feedback)
- "Import chains show cross_file_calls.py loads 300KB of unnecessary deps when only extract() is needed" (profiling data)

**Current justification:** "Hard to reason about as a single unit" — this is developer pain, not user pain. Users don't care about internal module size unless it degrades their experience.

**Severity:** MEDIUM — Solution may be solving the wrong problem

---

### Scope Creep: New Features Bundled With Extraction

**MVP claim:** "Extract project-level analysis into intermap"

**Actual scope:**
- F1-F3: Pure extraction (aligned with MVP)
- F4: Project registry (new feature, not extraction)
- F5: Agent overlay (new feature, not extraction)
- F6: Marketplace packaging (infrastructure, not user-facing)

**Problem:** F4 and F5 are genuinely valuable **new capabilities**, not just code reorganization. Bundling them with the extraction obscures their value and inflates delivery risk.

**Alternative scope:**
- **Phase 1 (v0.1):** Project registry + agent overlay as **standalone intermap features**, zero extraction
- **Phase 2 (v0.2):** Extract analysis tools after registry proves useful and adoption is validated

**Benefit:** Validate user value before incurring migration cost

**Severity:** MEDIUM — Increases delivery risk without validating value first

---

### Opportunity Cost: What Else Could This Sprint Deliver?

**Effort estimate (from PRD):**
- 6 Python modules to extract and decouple (~2-3 days)
- Go MCP scaffold + subprocess bridge (~1-2 days)
- Remove tools from tldr-swinton without breaking existing users (~1 day)
- Marketplace packaging (~1 day)
- Testing across 27 plugins (~1-2 days)
- **Total: ~7-10 days**

**Alternative investments with clearer user value:**
- Implement task-prompted codemaps (explicitly deferred to v0.2, but users want it)
- Improve tldr-swinton cold-start performance (if size is actually the blocker)
- Add better tool descriptions/examples so agents know when to call what
- Build intermap's project registry **without** extracting anything

**Missing from PRD:** Success criteria, user validation plan, rollback plan

**Severity:** MEDIUM — May not be highest-priority use of sprint bandwidth

---

## Flow Analysis

### Critical Flow: Agent Chooses Which Plugin to Call

**Entry point:** Agent receives analysis task

**Happy path (PRD assumes):**
1. Agent reads task: "Find all callers of `authenticate()` before refactoring"
2. Agent recognizes this is "project-level analysis"
3. Agent calls `intermap::impact("authenticate")`
4. Agent receives caller tree
5. Agent proceeds with refactoring

**Reality check:**
- Step 2 assumes agent has been trained that "callers = project-level"
- Step 3 assumes agent knows intermap exists and owns `impact()`
- No mechanism described for step 2 or step 3

**Failure path #1: Agent guesses wrong plugin**
1. Agent reads task
2. Agent searches available tools for "impact"
3. Finds `tldr_swinton::impact` (cached in memory from previous session)
4. Calls it → **tool not found** (removed in F3)
5. Agent retries with different tool
6. Eventually discovers `intermap::impact` via trial and error
7. **User loses 3-5 turns to tool discovery**

**Failure path #2: Agent doesn't discover intermap**
1. Agent reads task
2. Agent searches for "callers"
3. Doesn't find `impact()` in tldr-swinton (removed)
4. Falls back to manual `Grep` across all files
5. **User gets degraded experience, doesn't know better tool exists**

**Missing states:**
- What happens if both plugins are installed but one is stale?
- What if agent has intermap but not tldr-swinton (or vice versa)?
- What if intermux is down and agent overlay fails?

**Missing transitions:**
- How does agent learn intermap exists?
- How does agent decide when to use intermap vs. tldr-swinton?
- What's the fallback if agent can't call MCP tools?

**Recommendation:** Define and test these flows before shipping

---

### Critical Flow: Existing Hook Calls Removed Tool

**Entry point:** Agent edits a function using Serena `replace_symbol_body`

**Current happy path:**
1. PreToolUse hook fires
2. Hook calls `tldrs impact <function>` via daemon
3. Agent sees "15 callers will be affected"
4. Agent proceeds with edit, aware of blast radius

**Post-extraction broken path:**
1. PreToolUse hook fires
2. Hook calls `tldrs impact <function>`
3. **Tool not found** (removed in F3)
4. Hook exits with error (or silently fails?)
5. Agent proceeds with edit **without seeing blast radius**
6. Regression: Safety feature silently degrades

**PRD claims (F3 acceptance criteria):**
> - [ ] Daemon command handlers for these tools removed or no-op'd

**"No-op'd" is ambiguous:**
- Returns empty result? (Silent failure, bad)
- Returns error message? (Breaks workflow, bad)
- Redirects to intermap? (Requires intermap installed, complex)

**Missing from PRD:**
- Hook migration strategy
- Backward-compatibility testing checklist
- Graceful degradation plan

**Recommendation:** Require hook migration plan before F3 begins

---

## Evidence Standards

### Data-Backed Findings
✅ **Plugin count verified:** 27 plugins in Interverse (from AGENTS.md)
✅ **Tool names confirmed:** `arch`, `calls`, `dead`, `impact`, `change_impact`, `diagnostics` exist in tldr-swinton MCP server (from grep)
✅ **File sizes confirmed:** `cross_file_calls.py` is 117KB, `durability.py` is 12KB (from ls)

### Assumption-Based Reasoning
⚠️ **Agent discoverability:** Assumed agents will fail to discover intermap without explicit guidance (based on generic UX heuristics, not Interverse-specific user research)
⚠️ **Migration pain:** Assumed existing workflows will break (based on PRD acceptance criteria, not actual workflow testing)
⚠️ **Value perception:** Assumed agents won't understand why to use intermap (based on missing value prop in PRD, not user interviews)

### Unresolved Questions
❓ **How many active sessions/workflows currently use tldr-swinton's `impact/arch/calls` tools?** (Could invalidate migration urgency)
❓ **What % of agents have both tldr-swinton and intermap installed post-launch?** (Affects co-existence strategy)
❓ **Do agents actually struggle with tldr-swinton's size/complexity today?** (Evidence gap)

---

## Decision Lens

### Trade-offs (Made Explicit)

**If we proceed as-is:**
- ✅ Cleaner internal architecture (developer benefit)
- ✅ New capabilities (project registry, agent overlay)
- ❌ Existing workflows break without migration plan
- ❌ Agents can't discover which plugin does what
- ❌ Low adoption due to unclear value prop

**If we defer extraction, ship registry first:**
- ✅ Validate value before incurring migration cost
- ✅ No workflow breakage
- ✅ Clearer messaging ("new plugin for project mapping")
- ❌ tldr-swinton stays big (if that's actually a problem)
- ❌ Delays internal cleanup

**If we add disambiguation/migration:**
- ✅ Smooth transition for existing users
- ✅ Clear agent decision criteria
- ✅ Reduced support burden
- ❌ Adds ~2-3 days to timeline
- ❌ Requires coordination across hook/skill updates

---

## Recommendations

### 1. BLOCK until discoverability is addressed

**Required before proceeding:**
- [ ] Define tool naming convention so agents can tell plugins apart
  - Example: Rename tools to `intermap_arch()`, `intermap_calls()`, etc.
  - Or: Add explicit "Use intermap for project-level, tldr-swinton for file-level" to tool descriptions
- [ ] Add onboarding mechanism
  - SessionStart hook that announces intermap's existence when installed
  - Skill that explains when to use each plugin
  - Help text in every moved tool explaining the split
- [ ] Test agent workflows in realistic scenarios
  - Can agents discover intermap without being told?
  - Do agents call the right plugin for the right task?

### 2. REQUIRE migration plan before F3

**Required deliverables:**
- [ ] Hook migration checklist (which hooks call which tools, how to update)
- [ ] Backward-compatibility strategy (shims? redirects? error messages?)
- [ ] Deprecation timeline (how long do both plugins coexist?)
- [ ] Rollback plan (what if adoption fails?)

### 3. Separate value from extraction

**Proposed phasing:**
- **Phase 0.1 (2-3 days):** Ship project registry + agent overlay as **new intermap features**, zero extraction
  - Validate: Do agents use `project_registry()`? Do they find agent overlay useful?
- **Phase 0.2 (5-7 days):** Extract analysis tools **only if registry proves valuable**
  - By this point, agents already know intermap exists
  - Migration is additive (new tools in familiar plugin) not disruptive (tools disappear from old plugin)

### 4. Add success metrics

**Required before claiming "done":**
- [ ] % of agents with intermap installed (target: 80%+ within 2 weeks)
- [ ] Tool call frequency: `intermap::*` vs. `tldr_swinton::*` (target: 50/50 split)
- [ ] Error rate for moved tools (target: <5% tool-not-found errors)
- [ ] User feedback: Do agents report value from project registry/overlay? (target: 3+ positive mentions)

---

## Appendix: Missing User-Facing Documentation

**What agents need to know (not in PRD):**

### When to use intermap
- "Use **intermap** when analyzing cross-project dependencies, architecture layers, or coordinating with other agents"
- "Use **tldr-swinton** when extracting file contents, understanding symbol relationships, or getting compact context"

### What's new in intermap
- "See all projects in your workspace at a glance with `project_registry()`"
- "Avoid conflicts by checking which agents are editing what with `agent_map()`"
- "Understand your codebase architecture with `arch()`, `calls()`, `dead()` analysis"

### How to migrate
- "Previously used `/tldrs-arch`? Now use `/intermap:arch`"
- "Hooks that called `tldrs impact` now call `intermap impact`"
- "Both plugins can coexist during transition — install intermap alongside tldr-swinton"

**None of this exists in the PRD.**

---

## Final Verdict

**BLOCK** — Do not proceed with extraction until:
1. Discoverability mechanism defined and tested
2. Migration plan documented with rollback strategy
3. User value proposition clearly articulated
4. Success metrics established

**Alternative path:** Ship project registry + agent overlay as v0.1 (no extraction), validate adoption, then extract in v0.2 if users find value.

**High-confidence prediction:** If shipped as-is, <30% of agents will discover/use intermap within 1 month, and existing tldr-swinton workflows will degrade silently.
