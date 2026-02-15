---
date: 2026-02-13
type: quality_review
component: plugin_enforcement_architecture
scope: implementation_quality_and_engineering_tradeoffs
reviewer: flux-drive
---

# Quality Review: tldrs Enforcement Approaches

## Executive Summary

The current tldr-swinton plugin implementation has decent hook code quality but fundamentally misaligned expectations. The hooks work correctly when they fire, but they're solving the wrong problem — they provide additional context AFTER tool use rather than preventing expensive operations BEFORE they happen. The 24 MCP tools represent a better foundational layer, but the plugin architecture built on top duplicates effort and creates cognitive load. Of the four proposed directions, **Direction 4 (Simplify tools + improve descriptions)** offers the highest quality-to-effort ratio, followed by targeted CLAUDE.md rules for workflow guidance.

**Quality Grade: C+** — Production-ready bash scripts, solid deduplication patterns, but architectural mismatch between what hooks CAN do vs what the project NEEDS them to do.

## Current Implementation Quality Assessment

### Hook Scripts Quality: B+

**What's Good:**
- **Robust error handling:** `set +e` with `exit 0` fallback is correct for hooks that must never break the UX
- **Deduplication pattern works:** `/tmp/tldrs-{hook}-{session_id}-{hash}` flag files prevent redundant runs
- **Timeout awareness:** `timeout 5` wrapping all tldrs calls respects the 8s hook timeout budget
- **JSON output correctness:** Python `json.dumps()` for additionalContext avoids bash string escaping bugs
- **Symbol extraction logic:** The sed pipeline in `pre-serena-edit.sh` correctly handles name_path formats

**What's Fragile:**
- **Bash→jq→python3 pipeline:** Three-stage pipeline fails silently if any component is missing or errors
- **md5sum for hashing:** Works but non-portable (BSD vs GNU). `sha256sum` would be more consistent
- **Silent failure mode:** `|| exit 0` on every error means hooks never report problems — debugging requires log files
- **Hardcoded paths:** `/tmp/tldrs-*` works on Linux but fails on macOS with stricter /tmp sandboxing

**Verdict:** These are **production-quality bash scripts** for their intended purpose. The pipeline approach is appropriate for the 8s timeout constraint. The silent-failure pattern is correct for hooks (must never block the agent).

### Hook Architecture Quality: D

**Fundamental Mismatch:**

The hooks follow a **PostToolUse reactive pattern** — they add context AFTER the agent has already committed to an expensive operation:

```
Agent: "Let me Read this 1000-line file"
CC: <reads entire file, 15000 tokens>
PostToolUse hook: "Here's a 500-token extract summary as additionalContext"
Result: Agent has BOTH the full file AND the extract (15500 tokens total)
```

What the project actually needs is a **PreToolUse preventive pattern**:

```
Agent: "Let me Read this 1000-line file"
PreToolUse hook: "STOP. Run `tldrs extract <file>` first (500 tokens), decide if you still need the full Read"
Result: Agent uses extract, avoids the 15000-token Read
```

But Claude Code's PreToolUse hook API **blocks the original tool call** during hook execution, creating a 3-8 second UX freeze. This is why the project pivoted to PostToolUse — but that means the hooks can't prevent expensive operations, only add MORE context afterward.

**The Setup Hook Promise:** The setup.sh script says "The tldrs-session-start skill will run diff-context when you begin coding." This promise is never kept — skills fire based on Claude's heuristic trigger matching, not on a guaranteed timeline.

**Evidence from session logs:** The `/tmp/tldrs-impact-*` and `/tmp/tldrs-extract-*` files show hook deduplication works, but there's no evidence in real sessions of agents CHANGING BEHAVIOR because of hook output.

### MCP Server Quality: A-

**Count:** 24 tools registered (not 31 — the user's prompt had stale data)

```
tree, structure, search, extract, context, cfg, dfg, slice, impact, dead, arch,
calls, imports, importers, semantic, diagnostics, change_impact, delegate,
verify_coherence, diff_context, structural_search, distill, hotspots, status
```

**What's Good:**
- Clean 1:1 mapping with CLI commands — no abstraction mismatch
- Daemon auto-start with socket liveness check — robust process management
- Response envelope unwrapping — MCP tools return clean data, not `{"status": "ok", "result": ...}` wrappers
- Type hints on all tool functions — self-documenting API
- `_format_context_result()` handles both dict and string returns gracefully

**What's Overlapping:**
- `context` vs `diff_context` vs `delegate` vs `distill` — all return ContextPack-shaped data, just with different selection/compression heuristics
- `semantic` is just `find` — no clear differentiation
- `cfg`, `dfg`, `slice` are specialized views — correct to separate, but agents won't discover them

**Naming Issues:**
- `delegate` — unclear what this does from the name alone (answer: generates retrieval plan for a task description)
- `distill` — unclear what makes this different from `diff_context --preset minimal`
- `verify_coherence` — sounds like a validation check, not a context-generation tool

**Missing from tool descriptions:** Cost/token guidance. An agent sees 24 tools and no hint that `extract` costs ~500 tokens while `context` costs ~2000 tokens while `Read` costs ~15000 tokens.

**Verdict:** Well-engineered MCP server, but **too many tools with unclear differentiation**. Needs consolidation and cost-aware descriptions.

### Skills Quality: B

**What's Good:**
- **Decision trees not rules:** Skills lay out "if-this-then-that" workflows, not "never do X" prohibitions
- **Concrete examples:** Every branch shows the exact command to run
- **Well-scoped triggers:** Session-start, map-codebase, ashpool-sync each have clear trigger conditions
- **No duplication with hooks:** Skills correctly focus on strategy (which workflow?) not tactics (run extract before read)

**What's Missing:**
- **No escalation ladder:** Skills don't teach "try X (cheap), if not enough try Y (expensive)"
- **No cost awareness:** No mention of token costs for different approaches
- **Trigger unreliability acknowledged:** The session-start skill is supposed to auto-run diff-context but project knows this doesn't reliably happen

**Evidence of non-invocation:** The Setup hook promises "the session-start skill will run diff-context when you begin coding" — this is aspirational, not factual. Skills depend on Claude's heuristic matching and often don't fire.

**Verdict:** Skills are well-written but **low-impact due to opt-in nature**.

### Integration Quality: C-

**Version Sync:** The project has learned from past pain — `scripts/bump-version.sh` updates all 3 version locations (pyproject.toml, plugin.json, marketplace.json) atomically with pre-commit validation. This is good hygiene.

**Hook Error Label Bug:** Per MEMORY.md, Claude Code shows "PreToolUse:Read hook error" even when hooks exit 0 with valid output. The project knows this is a cosmetic CC bug (#17088, #16950). Correct to document and ignore.

**Hook stdin API:** Per `docs/solutions/integration-issues/claude-code-hook-stdin-api.md`, hooks receive JSON on stdin with `.session_id`, `.tool_input.file_path`, etc. The hooks use this correctly via `jq`.

**LFS Submodule Issue:** Per `docs/solutions/build-errors/lfs-submodule-blocks-plugin-install.md`, the `tldr-bench/data` submodule blocked plugin installs until `.gitmodules` was fixed with `update = none`. This is resolved.

**Stale Cache Problem:** Per `docs/solutions/build-errors/stale-plugin-cache-ghost-entries.md`, old plugin names accumulate in `~/.claude/plugins/cache/` as ghost entries. The project knows `claude plugin uninstall` can't remove them and manual `rm -rf` is required. This is a CC limitation, not a plugin bug.

**Verdict:** The project has **battle-tested integration knowledge** but is working around fundamental CC limitations (hook error labels, cache cleanup, PreToolUse blocking).

## Engineering Tradeoffs: The Four Directions

### Direction 1: Expand PreToolUse Hooks

**Proposed:** Add PreToolUse matchers for Edit, Write, Bash to inject context before every edit/write/command.

**Implementation Concerns:**

1. **Performance bottleneck:** PreToolUse blocks the original tool call. With 8s timeout, a `tldrs impact` or `tldrs context` call that takes 3-5s creates a 3-5s UX freeze on EVERY Edit/Write/Bash invocation. Agents will perceive this as "Claude Code is slow."

2. **Context pollution:** Not every edit needs call-graph analysis. Editing a JSON config file doesn't benefit from `tldrs impact`. Bash commands like `git status` or `npm install` don't need `tldrs diff-context`. The hook has no way to distinguish "editing core logic" from "editing a config file."

3. **Deduplication complexity:** The per-symbol flag pattern works for Serena (edits are symbol-scoped), but Edit/Write target files, and Bash is free-form text. Would need per-file flags for Edit/Write, but Bash has no stable identifier — `cd /tmp && tldrs context foo` vs `tldrs context foo` are different strings but same semantic operation.

4. **Timeout budget:** Running `tldrs impact` (3s) + `tldrs context` (2s) means 5s of the 8s budget consumed, leaving 3s for JSON formatting and return. If the tldrs daemon is cold-starting, this could exceed 8s and cause hook timeout → fallback to no context injection.

**Quality Assessment:**
- **Correctness:** Could be made to work with aggressive caching and fast-path checks
- **Maintainability:** High complexity — need per-tool heuristics for "does this edit/write/bash warrant context injection?"
- **UX impact:** HIGH RISK of introducing perceived slowness
- **Token savings:** Potentially high IF context injection prevents expensive operations, but no guarantee agents will act on the injected context

**Recommendation:** **Do not pursue.** The UX freeze risk outweighs potential token savings. If you want pre-edit context, use MCP tools with clear cost signals in descriptions so agents CHOOSE to call `tldrs impact` before editing, rather than forcing it via blocking hooks.

### Direction 2: CLAUDE.md Rules

**Proposed:** Add rules to CLAUDE.md like "Before editing any function, run `tldrs impact <symbol>` to check callers" or "Before reading files >300 lines, run `tldrs extract <file>`."

**Implementation Concerns:**

1. **Rule saturation:** Per global CLAUDE.md, "CLAUDE.md already has many rules — diminishing returns on adding more?" This is a real phenomenon. Agents have limited working memory for rules, and rules compete for attention. If CLAUDE.md grows beyond ~50 rules, later rules are effectively ignored.

2. **How to phrase for adherence:** Phrasing matters enormously. Compare:
   - ❌ "Consider using tldrs extract before reading large files" → ignored (too soft)
   - ❌ "You must run tldrs extract before Read" → triggers agent refusal ("I don't have permission to refuse user requests")
   - ✅ "For files >300 lines: `tldrs extract <file>` provides structure at 85% token savings vs raw Read. Use extract first unless user explicitly requests full file content."

3. **Testing adherence:** No programmatic way to verify rule-following short of running evals with real agents. The project has Ashpool for eval infrastructure, but eval coverage is for tldrs OUTPUT quality, not agent adherence to usage rules.

4. **Conflict with existing habits:** Agents have strong priors from training — "Read the file, then analyze it" is a deeply ingrained pattern. Rules that contradict trained behavior need STRONG justification in the rule text ("this saves 10,000 tokens" not "this is better").

**Quality Assessment:**
- **Correctness:** Rules are correct IF followed, but adherence is probabilistic
- **Maintainability:** Low cost to add rules, but high cost to validate they're working
- **UX impact:** Zero performance penalty (rules are just text)
- **Token savings:** Medium IF rules are followed; unclear adherence rate without evals

**Recommendation:** **Selectively pursue** for high-value, low-ambiguity rules:
- ✅ "For git diffs >100 lines: `tldrs diff-context --preset compact` reduces tokens by 50-73% vs raw `git diff` or Read of changed files. Start all diff-related tasks with diff-context."
- ✅ "Before calling Serena rename_symbol or replace_symbol_body: Run `tldrs impact <symbol> --depth 2` to identify callers that may break."
- ❌ Do NOT add per-file rules ("never Read >300 lines without extract") — hooks already handle this, and redundancy creates noise

### Direction 3: Hybrid (CLAUDE.md + Hooks)

**Proposed:** CLAUDE.md rules for high-level workflow + hooks for per-file tactics, with deduplication via shared flag files.

**Implementation Concerns:**

1. **Dedup coordination:** If CLAUDE.md says "run `tldrs context foo`" and agent does it, then PreToolUse hook also runs `tldrs impact foo`, they'd need a shared flag file namespace. Currently flags are `/tmp/tldrs-{hook}-{session_id}-{hash}`. Would need a convention like `/tmp/tldrs-operations-{session_id}/{hash}.json` with operation type + timestamp for both skill-driven and hook-driven operations.

2. **Redundant work risk:** If dedup isn't perfect, agent gets duplicate output. If dedup is too aggressive, agent misses useful context because the flag was set by a different operation (e.g., `tldrs context foo` sets a flag, then later the agent needs `tldrs impact foo` but the flag prevents it).

3. **Debugging complexity:** When something doesn't work, is it because (a) the rule wasn't followed, (b) the hook didn't fire, (c) the dedup flag prevented the operation, or (d) the tldrs command itself errored? Multiple layers = multiple failure modes.

4. **Maintenance burden:** Every new tldrs command or preset needs updates in BOTH CLAUDE.md rules AND hook logic. The project already has 4 files to sync for Ashpool (regression_suite.json, ab_formats.py, demo-tldrs.sh, score_tokens.py) — adding CLAUDE.md + hooks as a 5th and 6th sync target increases maintenance load.

**Quality Assessment:**
- **Correctness:** Could work with careful coordination, but complex
- **Maintainability:** HIGH COST — two layers to maintain, dedup to coordinate, multiple failure modes to debug
- **UX impact:** Hybrid of Direction 1 (hook slowness) + Direction 2 (zero perf penalty)
- **Token savings:** Potentially highest IF both layers work perfectly, but risk of redundant work

**Recommendation:** **Do not pursue.** Complexity outweighs benefits. The existing 4-layer architecture (CLI presets + skills + hooks + CLI self-hints) from `layered-enforcement-architecture-plugin-20260211.md` is already a hybrid — adding more coordination would tip into over-engineering.

### Direction 4: Simplify Tools + Improve Descriptions

**Proposed:** Reduce 24 MCP tools to 5-6 essential tools with cost-aware descriptions that guide agents toward token-efficient choices.

**Implementation Concerns:**

1. **Which tools to keep?** Propose:
   - ✅ **extract** (file structure, ~500 tokens) — foundational, no alternatives
   - ✅ **context** (symbol + callers/callees, ~2000 tokens) — core use case, subsumes cfg/dfg/slice for most cases
   - ✅ **diff_context** (changes + surrounding context, ~1500 tokens with preset) — replaces raw git diff + Read pattern
   - ✅ **find** (semantic search, ~50 tokens per result) — unique capability, no CLI equivalent
   - ✅ **structural_search** (ast-grep patterns, ~50 tokens per result) — unique capability, complements find
   - ❓ **distill** (compress context for sub-agents, ~1500 tokens output) — valuable but narrow use case
   - ❌ **delegate** — retire, replace with improved context description
   - ❌ **verify_coherence** — retire, make this a flag on diff_context
   - ❌ **cfg/dfg/slice** — retire as separate tools, make these flags on context (e.g., `context(..., include_cfg=true)`)
   - ❌ **semantic** — retire, it's an alias for find
   - ❌ **tree/structure/search** — keep as CLI-only, not MCP (agents have Read/Glob/Grep for these)

2. **Tool consolidation approach:** Instead of 24 separate tools, offer **6 core tools with flags**:
   ```python
   @mcp.tool()
   def context(
       project: str,
       entry: str,
       preset: str = "compact",  # compact | minimal | full
       depth: int = 2,
       include_cfg: bool = False,  # include control flow graph
       include_dfg: bool = False,  # include data flow graph
       ...
   ) -> str:
       """Get call graph context around a symbol.

       Costs: ~500 tokens (compact preset) vs ~2000 (full) vs ~15000 (reading the file raw).

       When to use:
       - BEFORE editing a function — see callers that might break
       - BEFORE reading a file — get structure first, then decide if you need full content
       - Multi-turn tasks: Use preset="compact" with --session-id for delta tracking

       Presets:
       - compact: signatures + types + key imports (~500 tokens)
       - minimal: ultracompact format + aggressive pruning (~300 tokens)
       - full: complete bodies + comments (~2000 tokens)
       """
   ```

3. **Description quality matters:** Compare:
   - ❌ "Get context for a symbol" → tells agent WHAT but not WHEN or WHY
   - ✅ "Get call graph context around a symbol. Costs ~500 tokens vs ~15000 for reading the file. Use BEFORE editing to see callers." → tells WHAT, WHEN, WHY, and COST

4. **Testing tool descriptions:** The MCP tool descriptions are visible to agents via `tools/list` but the project has no eval for "does agent pick the right tool?" Ashpool evals test OUTPUT quality, not SELECTION quality.

**Quality Assessment:**
- **Correctness:** Consolidation reduces surface area, fewer edge cases
- **Maintainability:** LOW COST — 6 tools vs 24, clear flag meanings, one description to maintain per tool
- **UX impact:** IMPROVED — fewer tools = less cognitive load, cost info in descriptions guides agents toward cheap operations first
- **Token savings:** Medium-High — IF descriptions successfully steer agents, but no enforcement

**Recommendation:** **PURSUE THIS FIRST.** Highest quality-to-effort ratio. Steps:
1. Consolidate 24 tools → 6-7 core tools with flags
2. Rewrite descriptions to include cost estimates and usage guidance
3. Add `buildInstructions()` hook (like qmd) to inject dynamic project state (index status, available presets, session-id recommendation)
4. Run Ashpool evals with "selection quality" metrics — track which tools agents choose for different task types

## Quality Questions Answered

### Q1: Are the hook scripts production-quality or prototype-quality?

**Answer:** Production-quality bash scripts for their intended purpose (PostToolUse context injection), but **architecturally misaligned** with the project's actual needs (PreToolUse prevention).

The scripts handle timeouts, deduplication, error handling, and JSON generation correctly. The problem is not code quality but strategic fit — the project needs enforcement, and PostToolUse hooks can't enforce, only advise.

### Q2: The bash→jq→python3 pipeline — robust or fragile?

**Answer:** Fragile by necessity, but **correct for the constraints**.

Why the pipeline is needed:
- Bash gets JSON from stdin (hook input)
- jq extracts fields (session_id, file_path, etc.)
- Python generates valid JSON output (bash can't reliably escape strings for JSON)

Why it's fragile:
- Three processes, three potential failure points
- Silent failures (`|| exit 0`) mean debugging requires log inspection
- Assumes jq and python3 are always available (true for Claude Code's environment, but not portable)

Could it be improved? Yes, by writing hooks in pure Python with `#!/usr/bin/env python3` shebangs and using `json.load(sys.stdin)`. But the bash pipeline is defensible given the 8s timeout budget (Python startup adds ~100ms, bash pipeline adds ~10ms).

### Q3: What's the test strategy for any of these approaches?

**Answer:** Currently **no automated tests for hook/skill effectiveness**. The project has:
- Unit tests for ContextPack JSON serialization (`tests/test_mcp_contextpack_json.py`)
- Ashpool evals for output quality (token efficiency, correctness)
- Manual testing of hook firing via `/tmp/tldrs-*` flag files

What's missing:
- Evals for "does agent use tldrs vs raw Read/Grep?"
- Evals for "does agent pick the right tldrs tool for the task?"
- Evals for "does agent use presets vs bare flags?"

How to add these:
1. Extend Ashpool to capture tool selection traces (which tools did the agent call?)
2. Define "correct" tool selection for benchmark tasks (e.g., "diff review should use diff-context not raw Read")
3. Score agents on selection correctness, not just output correctness

### Q4: Naming — 24 tools with overlapping names, is this confusing?

**Answer:** YES. Concrete confusion points:

| Tool | What it does | Confusion with |
|------|-------------|---------------|
| `semantic` | Semantic code search | `find` does the exact same thing |
| `delegate` | Generate retrieval plan | Sounds like "delegate to another agent," not "plan what to retrieve" |
| `distill` | Compress context for sub-agents | Sounds like "make shorter," doesn't clarify it's for sub-agent handoff |
| `context` | Symbol call graph | `diff_context` also returns ContextPack, unclear when to use which |
| `cfg` | Control flow graph | Agents don't know what CFG means without CS background |

Better naming:
- `semantic` → retire, it's an alias
- `delegate` → `plan_retrieval` or retire, fold into context description
- `distill` → `compress_for_handoff` or add clear description
- `context` + `diff_context` → clarify "use diff_context for changed code, context for arbitrary symbols"
- `cfg`/`dfg` → keep as flags on context, not standalone tools

### Q5: Error handling — `set +e` and `exit 0` on any failure. Is silent failure right?

**Answer:** YES for hooks, NO for general practice.

**Why it's correct for hooks:**
- Hooks MUST NOT break the user experience. If a hook errors, the worst outcome is "agent doesn't get extra context" not "agent's operation fails."
- The alternative (let hooks fail and show errors) means a buggy hook can break Read/Edit/Bash operations, which is unacceptable.
- Silent failure with logging (`/tmp/tldrs-hook-debug.log`) is the right tradeoff.

**Why it's wrong for general code:**
- Silent failures hide bugs — if tldrs CLI errors are swallowed, the user never knows why results are missing
- The MCP server correctly propagates errors as `{"status": "error", "message": "..."}` — this is good

**Where the pattern appears:**
- ✅ Hooks: `set +e; tldrs extract ... || exit 0` — correct
- ✅ Hook JSON generation: `python3 ... || exit 0` — correct
- ❌ CLI commands in skills: `tldrs context foo || echo 'failed'` — NEVER do this, let errors surface

## Test Strategy Recommendations

### Current State: No Hook/Skill Effectiveness Tests

The project tests:
1. MCP ContextPack JSON serialization (unit test)
2. Output quality and token efficiency (Ashpool evals)
3. Hook firing via flag file inspection (manual)

Missing:
1. Agent tool selection quality
2. Preset usage rate
3. Hook additionalContext impact on agent behavior

### Proposed Testing Approach

**Tier 1: Selection Quality Evals (High Value)**

Add to Ashpool:
```json
{
  "eval_type": "selection_correctness",
  "task": "Review git diff and identify breaking changes",
  "correct_tools": ["diff_context"],
  "incorrect_tools": ["Read", "Bash:git diff"],
  "scoring": {
    "correct_tool_used": 10,
    "incorrect_tool_used": -5,
    "no_tool_used": -10
  }
}
```

Track:
- Which tools did the agent call?
- Did it use presets or bare flags?
- Did it run cheap operations (extract, diff-context) before expensive ones (Read)?

**Tier 2: Regression Tests for Hook Firing (Medium Value)**

Add integration tests:
```python
def test_post_read_extract_fires_on_large_file():
    """Verify PostToolUse:Read hook injects extract output for >300 line files."""
    session_id = "test-session"
    file_path = "/tmp/large_file.py"
    # Create 400-line file
    with open(file_path, 'w') as f:
        f.write('\n'.join([f"# Line {i}" for i in range(400)]))

    # Simulate hook stdin
    hook_input = json.dumps({
        "session_id": session_id,
        "tool_name": "Read",
        "tool_input": {"file_path": file_path}
    })

    # Run hook
    result = subprocess.run(
        ["bash", ".claude-plugin/hooks/post-read-extract.sh"],
        input=hook_input.encode(),
        capture_output=True
    )

    # Verify additionalContext was returned
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "additionalContext" in output
    assert "tldrs extract" in output["additionalContext"]
```

**Tier 3: CLAUDE.md Rule Adherence Evals (Lower Value, High Cost)**

Only pursue if Tier 1 shows low selection quality. Would require:
- Benchmark tasks with ground-truth "correct" workflows
- Agent runs with/without CLAUDE.md rules
- Diff in tool selection patterns
- High eval cost (full agent runs), unclear ROI

## Final Recommendations

### Immediate Actions (Next 2 Weeks)

1. **Direction 4: Simplify + Cost-Aware Descriptions**
   - Consolidate 24 MCP tools → 6-7 core tools
   - Rewrite tool descriptions with cost estimates and usage guidance
   - Add `buildInstructions()` to inject project state dynamically
   - Estimated effort: 8-12 hours

2. **Selective CLAUDE.md Rules**
   - Add 2-3 high-value rules (diff-context for diffs, impact before edits)
   - Test phrasing for adherence ("this saves N tokens" framing)
   - Estimated effort: 2-3 hours

3. **Ashpool Selection Quality Evals**
   - Add 5-10 benchmark tasks with correct tool selection as ground truth
   - Track tool usage patterns across eval runs
   - Estimated effort: 6-8 hours

### Do Not Pursue

1. **Direction 1: Expand PreToolUse Hooks**
   - High UX freeze risk, context pollution, dedup complexity
   - 8s timeout budget too tight for 3-5s tldrs operations

2. **Direction 3: Hybrid with Shared Dedup**
   - Excessive complexity, maintenance burden, multiple failure modes
   - Existing 4-layer architecture already achieves coordination

### Long-Term Architecture (3-6 Months)

The MCP tool layer is the right foundation. Invest in:
1. **Tool consolidation** — 6 core tools is more learnable than 24
2. **Cost transparency** — every description includes token estimates
3. **Dynamic guidance** — `buildInstructions()` adapts to project state
4. **Selection evals** — measure WHICH tools agents choose, not just output quality
5. **Progressive disclosure** — start with extract/diff-context/find, introduce advanced tools (cfg/dfg/slice) only when needed

The goal is **agents choose the right tool because descriptions guide them**, not because hooks/rules force them. Enforcement should be rare (Serena pre-edit impact check), not routine (every Read/Edit/Bash).

## Appendix: Implementation Quality Rubric

| Component | Code Quality | Architecture Fit | Maintenance Burden | Impact |
|-----------|-------------|------------------|-------------------|--------|
| Hook Scripts | B+ | D | Low | Low (advisory only) |
| MCP Server | A- | A | Medium (24 tools) | Medium (IF used) |
| Skills | B | C | Low | Low (opt-in) |
| Setup Hook | B | D | Low | Low (one-shot) |
| Version Sync | A | A | Low | High (prevents drift) |
| Dedup Pattern | A | A | Low | High (prevents spam) |
| Error Handling | A | A | Low | High (never breaks UX) |
| Tool Descriptions | C | B | Medium | Medium (could be much better) |

**Overall Grade: C+** — Solid execution of a misaligned strategy. The code works as designed, but the design doesn't solve the adoption problem.

## References

- `docs/solutions/best-practices/layered-enforcement-architecture-plugin-20260211.md` — 4-layer defense-in-depth architecture (CLI presets + skills + hooks + CLI hints)
- `docs/solutions/best-practices/hooks-vs-skills-separation-plugin-20260211.md` — Separation of concerns: hooks for tactics, skills for strategy
- `docs/solutions/integration-issues/cli-plugin-low-agent-adoption-vs-mcp-20260211.md` — CLI+plugin vs MCP for agent adoption
- `docs/solutions/integration-issues/claude-code-hook-stdin-api.md` — Hook I/O constraints and API details
- MEMORY.md — Hook error label is a CC UI bug (#17088), dedup patterns work, version sync critical
