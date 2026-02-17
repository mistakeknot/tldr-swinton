# fd-prompt-engineering: Token Waste Review

**Date:** 2026-02-12
**Reviewer:** fd-prompt-engineering (flux-drive)
**Scope:** Claude Code plugin integration — skills, commands, hooks, routing

---

## Executive Summary

The tldr-swinton plugin's total prompt injection footprint is **~6,040 tokens** across 13 files. This is moderate for a plugin of this complexity, but there are concrete savings available. The biggest issues are:

1. **AGENTS.md lists 3 retired skills** that no longer exist (~50 tokens of stale context, but damaging to routing accuracy)
2. **Command markdown duplicates MCP tool descriptions** (~350 tokens of pure redundancy)
3. **Setup hook outputs dynamic content** that overlaps with the `tldrs-session-start` skill (~200-400 tokens of per-session waste)
4. **Legacy suggest-recon.sh** is unreferenced but still on disk (524 tokens of dead code)
5. **interbench sync skill** is the largest single file at ~950 tokens and could be ~30% shorter

**Total estimated recoverable tokens: ~800-1,200 per session** from prompt injection, plus ~200-400 per session from setup hook output reduction.

---

## 1. Skill Token Budgets

### File: `.claude-plugin/skills/tldrs-session-start/SKILL.md`
- **Size:** 2,137 chars / ~610 tokens
- **Assessment: Mostly well-structured. Minor waste.**

**Good:**
- Decision tree format is excellent for agent routing
- "When to Skip" section prevents unnecessary activation
- Bash code blocks are appropriately terse

**Waste identified:**

| Location | Issue | Tokens wasted |
|----------|-------|---------------|
| Lines 3-4 (description) | 46-word description is long for frontmatter; Claude uses it for routing. Could be ~25 words. | ~15 |
| Lines 47-52 (Section 4: subagent) | `tldrs distill` for subagent consumption is a niche use case that fires on every session-start. Could be a separate skill or removed. | ~50 |
| Lines 54-59 (Section 5: test impact) | `tldrs change-impact` is useful but could be a one-liner instead of 4 lines. | ~20 |
| Line 65-66 | "Always use `--preset compact` unless you have a reason not to" repeats what's in the code blocks above. | ~15 |

**Subtotal waste:** ~100 tokens (~16%)

**Recommendation:** Remove Section 4 (subagent distill — this is a power-user feature, not session-start). Condense Section 5 to one line. Trim the description frontmatter.

---

### File: `.claude-plugin/skills/tldrs-map-codebase/SKILL.md`
- **Size:** 1,571 chars / ~448 tokens
- **Assessment: Well-scoped and concise. Minimal waste.**

**Good:**
- Clean decision tree
- "When to Skip" prevents unnecessary activation
- Short and actionable

**Waste identified:**

| Location | Issue | Tokens wasted |
|----------|-------|---------------|
| Lines 3-4 (description) | 48-word description. Could be ~25 words. | ~15 |
| Lines 40-43 (Workflow) | Numbered workflow repeats the decision tree content above it almost verbatim. | ~40 |

**Subtotal waste:** ~55 tokens (~12%)

**Recommendation:** Remove the "Workflow" section (lines 40-43) — it's a summary of the decision tree that was just shown. The agent doesn't need the same steps listed twice.

---

### File: `.claude-plugin/skills/tldrs-interbench-sync/SKILL.md`
- **Size:** 3,324 chars / ~950 tokens
- **Assessment: Largest skill. Contains template patterns that may be overtrained.**

**Good:**
- Step-by-step protocol is clear
- "Common Errors" section is valuable for guardrails

**Waste identified:**

| Location | Issue | Tokens wasted |
|----------|-------|---------------|
| Lines 44-57 (regression_suite.json patterns) | Full JSON template with 7 fields. Claude can infer the pattern from reading the existing file. | ~80 |
| Lines 59-63 (ab_formats.py patterns) | Python snippet for a simple list append. Claude can figure this out. | ~30 |
| Lines 65-82 (demo-tldrs.sh patterns) | Full bash template block (18 lines). Claude can match the existing style. | ~80 |
| Lines 84-95 (score_tokens.py patterns) | Python function template. | ~40 |

**Subtotal waste:** ~230 tokens (~24%)

**Recommendation:** Replace the full template blocks with one-line descriptions referencing the existing patterns in the files. Example: "Match the existing entry format in each file. Use `truncate_output` as the default entry." The skill already instructs Claude to read all 4 files (Step 3), so it will see the patterns.

---

### Skills Total

| Skill | Size (tokens) | Waste (tokens) | Waste % |
|-------|--------------|----------------|---------|
| session-start | ~610 | ~100 | 16% |
| map-codebase | ~448 | ~55 | 12% |
| interbench-sync | ~950 | ~230 | 24% |
| **Total** | **~2,008** | **~385** | **19%** |

---

## 2. Command Markdown Overhead

Commands are injected only when a user explicitly invokes a slash command, so their token cost is per-invocation, not per-session. This makes them lower priority.

### File: `.claude-plugin/commands/find.md` (~198 tokens)
- **Assessment: Clean and minimal.** The "Tips" section adds value. No significant waste.

### File: `.claude-plugin/commands/diff-context.md` (~312 tokens)
- **Waste:** "When to use" section (3 bullets, lines 24-27) is obvious from the description. ~30 tokens.
- "Tips" section (lines 29-32) repeats information from the MCP `diff_context` tool description (delta mode, JSON format). ~40 tokens.

### File: `.claude-plugin/commands/context.md` (~352 tokens)
- **Waste:** "When to use" section (lines 26-29) repeats the description. ~30 tokens.
- "Tips" about `--format ultracompact` and `--delegate` (lines 31-34) partially duplicates the MCP `context` and `delegate` tool descriptions. ~30 tokens.

### File: `.claude-plugin/commands/structural.md` (~284 tokens)
- **Waste:** The "Pattern syntax" section (lines 22-24) and "Examples" (lines 26-29) are **nearly identical** to the MCP `structural_search` tool description docstring. This is pure duplication. ~60 tokens.

### File: `.claude-plugin/commands/quickstart.md` (~104 tokens)
- **Assessment: Excellent. Minimal wrapper around a CLI call.** No waste.

### File: `.claude-plugin/commands/extract.md` (~199 tokens)
- **Waste:** "When to use" section (lines 17-19) is generic. ~20 tokens.
- "Tips" about combining with `tldrs cfg` (line 24) is useful and not duplicated.

### Commands Total

| Command | Size (tokens) | Waste (tokens) | Waste % |
|---------|--------------|----------------|---------|
| find.md | ~198 | ~0 | 0% |
| diff-context.md | ~312 | ~70 | 22% |
| context.md | ~352 | ~60 | 17% |
| structural.md | ~284 | ~60 | 21% |
| quickstart.md | ~104 | ~0 | 0% |
| extract.md | ~199 | ~20 | 10% |
| **Total** | **~1,449** | **~210** | **14%** |

**Key finding: MCP tool description duplication.** The MCP server (`mcp_server.py`) already provides rich docstrings for `diff_context`, `context`, `structural_search`, etc. These docstrings are sent to Claude as tool descriptions. When a user also invokes `/tldrs-structural`, Claude gets the pattern syntax TWICE: once from the MCP tool listing and once from the command markdown. The command files should contain only what's DIFFERENT from the MCP description (e.g., the bash invocation template and argument substitution).

---

## 3. Setup Hook Output Analysis

### File: `.claude-plugin/hooks/setup.sh` (~804 tokens of script)
- **What it outputs at session start:** Dynamic content that varies by project state.

**Output path 1 — project with changes (most common):**
```
Project: tldr-swinton (42 Python files, 3 changed since last commit)
Semantic index: ready
Changed files: src/foo.py, src/bar.py, tests/test_foo.py

[... tldrs diff-context output, typically 500-2000 tokens ...]

Available presets: compact, minimal, multi-turn
```

**Output path 2 — clean working tree:**
```
Project: tldr-swinton (42 Python files, 0 changed since last commit)
Semantic index: ready

[... tldrs structure output, typically 200-1000 tokens ...]

Available presets: compact, minimal, multi-turn
```

**Output path 3 — fallback:**
```
Project: tldr-swinton (42 Python files, 0 changed since last commit)
Semantic index: ready

Run 'tldrs diff-context --project . --preset compact' before reading code.
Use 'tldrs extract <file>' for file structure.

Available presets: compact, minimal, multi-turn
```

**Waste analysis:**

| Issue | Tokens | Severity |
|-------|--------|----------|
| **Overlap with `tldrs-session-start` skill**: The setup hook runs `tldrs diff-context --project . --preset compact` (line 55). The `tldrs-session-start` skill ALSO tells Claude to run `tldrs diff-context --project . --preset compact`. If the skill fires, the same analysis runs twice. | 500-2000 per duplicate run | **HIGH** |
| "Available presets: compact, minimal, multi-turn" (line 84) | ~10 | LOW |
| ast-grep warning (line 18) is useful only when missing | ~15 when fired | LOW |

**Subtotal waste:** 500-2000 tokens when both setup hook and session-start skill fire on the same session.

**Recommendation:** The setup hook should NOT run `tldrs diff-context`. It should only:
1. Check tldrs is installed (keep)
2. Check ast-grep availability (keep, but only on first install)
3. Run `tldrs prebuild` in background (keep)
4. Report project stats (file count, change count, index status) — 1-2 lines
5. Remove the diff-context/structure output entirely — let the skill handle it

This would reduce setup hook output from 500-2000 tokens to ~30-50 tokens, and eliminate the duplication with `tldrs-session-start`.

---

## 4. Hook Decision Overhead

### File: `.claude-plugin/hooks/pre-serena-edit.sh` (~668 tokens of script)
- **When it fires:** Before `replace_symbol_body` or `rename_symbol` (Serena MCP tools)
- **What it outputs:** JSON with `additionalContext` containing `tldrs impact` caller analysis

**Output example:**
```json
{"additionalContext": "tldrs caller analysis for MyClass/my_method (before replace_symbol_body):\n[impact output...]\n\nReview callers above before proceeding. Update callers if the change breaks their assumptions."}
```

**Assessment: Well-designed with good guardrails.**

| Feature | Assessment |
|---------|-----------|
| Per-symbol-per-session flagging (lines 33-38) | Good — prevents repeat analysis |
| 5-second timeout (line 41) | Appropriate |
| Silent failure on all error paths | Good — never blocks edits |
| Leaf symbol extraction from name_path (lines 19-24) | Necessary |

**Waste:**

| Issue | Tokens | Severity |
|-------|--------|----------|
| "Review callers above before proceeding. Update callers if the change breaks their assumptions." (line 62) is a generic instruction that Claude already knows to do. | ~20 per firing | LOW |
| The Python JSON-encoding block (lines 56-64) could use `jq` instead for fewer subprocess spawns | 0 (runtime, not prompt) | N/A |

**Subtotal waste:** ~20 tokens per Serena edit (minor).

### File: `.claude-plugin/hooks/post-read-extract.sh` (~586 tokens of script)
- **When it fires:** After every `Read` tool call
- **What it outputs:** `tldrs extract` output for files >300 lines, once per file per session

**Assessment: Well-targeted with appropriate thresholds.**

- 300-line threshold (line 31) is reasonable
- File type exclusion (lines 21-25) prevents firing on non-code files
- Per-file flagging prevents duplicates

**Waste:** None significant. The output is genuinely useful for large files.

### File: `.claude-plugin/hooks/suggest-recon.sh` (~524 tokens of script)
- **Status: DEAD CODE.** Not registered in `hooks.json`. Still on disk.
- **Assessment: Should be deleted.** It was the legacy PreToolUse hook for Read/Grep that has been replaced by the session-start skill + setup hook.

**Waste:** 524 tokens of dead code on disk (not injected, but adds to repo maintenance burden).

---

## 5. Routing Efficiency

### Skill-to-Skill Overlap

| Scenario | Skills that could fire | Overlap? |
|----------|----------------------|----------|
| "Fix this bug in auth.py" | session-start | No overlap |
| "What does this codebase do?" | session-start + map-codebase | **YES — both fire** |
| "Explore this repo structure" | map-codebase | No overlap |
| "Sync interbench coverage" | interbench-sync | No overlap |

**Overlap case: "understand/explore/onboard" tasks trigger both session-start and map-codebase.**

The `session-start` description says: "Also use when... onboarding to a repo."
The `map-codebase` description says: "Use when asked to... onboard to a new repo."

When both fire, the agent runs:
1. `tldrs diff-context` (from session-start)
2. `tldrs arch` + `tldrs structure` (from map-codebase)

This is actually correct behavior for onboarding — you want both diff context and architecture. But the descriptions overlap, which means Claude might invoke both when only one is appropriate, wasting the routing decision.

**Recommendation:** Clarify the routing boundary:
- `session-start`: "Use when starting **work** (fixing, implementing, debugging, reviewing)."
- `map-codebase`: "Use when asked to **understand** (what is this, show structure, architecture)."
- Remove "onboarding" from session-start's description; it's more map-codebase territory.

### Setup Hook + Skill Double-Fire (the biggest routing issue)

**This is the #1 routing problem.** The setup hook runs `diff-context` proactively. Then the session-start skill fires and tells Claude to run `diff-context` again. The agent gets the same information twice.

```
Session start:
  1. setup.sh fires → runs diff-context → output injected (~1000 tokens)
  2. User says "fix the bug in auth.py"
  3. session-start skill fires → tells Claude to run diff-context again → ~1000 tokens
  Total: ~2000 tokens for the same information
```

**Fix:** Either:
- (A) Remove diff-context from setup.sh (recommended — let the skill decide)
- (B) Have setup.sh set a flag file that the skill checks ("setup already ran diff-context")

Option A is simpler and more correct. The setup hook should be lightweight (install checks + prebuild). The skill should make the intelligent routing decision about what to run.

---

## 6. Meta-Instruction Waste (MCP Duplication)

This section identifies where skills/commands contain instructions that duplicate MCP tool descriptions from `mcp_server.py`.

### Finding 6a: structural.md vs MCP `structural_search` tool description

**Command file** (`.claude-plugin/commands/structural.md`, lines 22-29):
```markdown
**Pattern syntax:**
- `$VAR` matches any single AST node
- `$$$ARGS` matches zero or more nodes
- Patterns are language-aware (Python `def`, JS `function`, Go `func`, etc.)

**Examples:**
- Functions returning None: `'def $FUNC($$$ARGS): $$$BODY return None'`
- All method calls: `'$OBJ.$METHOD($$$ARGS)'`
- Go error handling: `'if err != nil { $$$BODY }'`
```

**MCP tool description** (mcp_server.py, lines 654-670):
```
Unlike regex search, this matches code *structure*. Use meta-variables:
- $VAR matches any single node
- $$$ARGS matches multiple nodes (variadic)

Example patterns:
- "def $FUNC($$$ARGS): $$$BODY return None" — functions that return None
- "if $COND: $$$BODY" — all if statements
- "$OBJ.$METHOD($$$ARGS)" — all method calls
```

**Overlap: ~60 tokens of near-identical content.** The MCP description is always available to Claude. The command file only adds the Go example and "language-aware" note.

### Finding 6b: context.md vs MCP `context` tool description

**Command file** tips about `--format ultracompact`, `--depth`, and `--delegate` all appear in the MCP tool's docstring parameter descriptions.

**Overlap: ~30 tokens.**

### Finding 6c: diff-context.md vs MCP `diff_context` tool description

**Command file** tips about `--session-id` and `--format json` are in the MCP tool's docstring.

**Overlap: ~40 tokens.**

### Finding 6d: session-start SKILL.md vs MCP tool descriptions

The skill mentions `tldrs impact`, `tldrs find`, `tldrs context`, `tldrs distill`, `tldrs change-impact` — all of which have MCP tool descriptions. However, the skill uses these in a decision-tree context (when to use each), which adds value beyond the tool descriptions. **This is NOT waste** — orchestration context is different from tool capability descriptions.

### Meta-Instruction Waste Total

| Source | Duplicated tokens |
|--------|-------------------|
| structural.md vs MCP structural_search | ~60 |
| context.md vs MCP context | ~30 |
| diff-context.md vs MCP diff_context | ~40 |
| **Total** | **~130** |

---

## 7. Stale Documentation (AGENTS.md)

### Finding 7a: AGENTS.md lists 6 skills but only 3 exist

**File:** `AGENTS.md`, lines 88-94

```markdown
| `tldrs-session-start` | Before reading code for bugs, features, refactoring, tests, reviews, migrations |
| `tldrs-find-code` | Searching for code by concept, pattern, or text |
| `tldrs-understand-symbol` | Understanding how a function/class works, its callers, dependencies |
| `tldrs-explore-file` | Debugging a function, tracing control/data flow, analyzing file structure |
| `tldrs-map-codebase` | Understanding architecture, exploring unfamiliar projects, onboarding |
| `tldrs-interbench-sync` | Syncing interbench eval coverage after tldrs capability changes |
```

The skills `tldrs-find-code`, `tldrs-understand-symbol`, and `tldrs-explore-file` were retired (replaced by MCP tools, per MEMORY.md and commit ae23075). But AGENTS.md still lists them. This is not token waste in the plugin, but it is **misleading documentation** that could confuse agents reading AGENTS.md.

### Finding 7b: AGENTS.md hook description is stale

**File:** `AGENTS.md`, lines 97-98

```markdown
- `PreToolUse` on **Read** and **Grep**: Suggests running tldrs recon before reading files (once per session via flag file)
```

This is wrong. The current `hooks.json` has:
- `Setup` → `setup.sh`
- `PreToolUse` on `mcp__plugin_serena_serena__replace_symbol_body` → `pre-serena-edit.sh`
- `PreToolUse` on `mcp__plugin_serena_serena__rename_symbol` → `pre-serena-edit.sh`
- `PostToolUse` on `Read` → `post-read-extract.sh`

The Read/Grep PreToolUse hook (`suggest-recon.sh`) is **not registered** in `hooks.json`. AGENTS.md is wrong.

---

## 8. Consolidated Recommendations

### Priority 1: Fix the Setup Hook / Session-Start Double-Fire (~1000-2000 token savings per session)

**File:** `.claude-plugin/hooks/setup.sh`

Remove the diff-context and structure execution (lines 51-63). Keep only:
- tldrs install check
- ast-grep check
- prebuild in background
- Project stats (file count, change count, index status)

This is the single highest-impact change. It eliminates duplicate diff-context runs and reduces setup output from ~1000 tokens to ~50 tokens.

### Priority 2: Trim interbench Sync Skill Templates (~230 token savings)

**File:** `.claude-plugin/skills/tldrs-interbench-sync/SKILL.md`

Replace full template blocks (Steps 4a-4d) with one-line descriptions. The skill already instructs Claude to read all 4 target files, so it will see the actual patterns.

### Priority 3: Remove MCP-Duplicated Content from Commands (~130 token savings)

**Files:** `structural.md`, `context.md`, `diff-context.md`

Strip "Pattern syntax", "Examples", "Tips" sections that duplicate MCP tool descriptions. Keep only the bash invocation template and argument substitution.

### Priority 4: Fix AGENTS.md Stale References (accuracy, not tokens)

**File:** `AGENTS.md`

- Remove the 3 retired skills from the table (lines 90-92)
- Fix the hook description (line 97-98) to match current hooks.json

### Priority 5: Delete Dead Code

**File:** `.claude-plugin/hooks/suggest-recon.sh`

Delete this file. It is not registered in `hooks.json` and adds maintenance burden.

### Priority 6: Clarify Routing Boundaries (~15 token savings + better accuracy)

**Files:** `tldrs-session-start/SKILL.md`, `tldrs-map-codebase/SKILL.md`

Remove "onboarding" from session-start's description. It belongs in map-codebase.

### Priority 7: Trim Session-Start Niche Sections (~70 token savings)

**File:** `tldrs-session-start/SKILL.md`

Remove Section 4 (subagent distill). Condense Section 5 (test impact) to one line.

---

## Summary Table

| Category | Current tokens | Recoverable tokens | % Recoverable |
|----------|---------------|-------------------|---------------|
| Skills (3 files) | ~2,008 | ~385 | 19% |
| Commands (6 files) | ~1,449 | ~210 | 14% |
| Hooks (4 files) | ~2,583 | ~524 (delete suggest-recon.sh) | 20% |
| Setup hook output (per session) | ~1,000-2,000 | ~950-1,950 | ~95% |
| **Static total** | **~6,040** | **~1,119** | **19%** |
| **Per-session dynamic waste** | **~1,000-2,000** | **~950-1,950** | **~95%** |

The **per-session dynamic waste** from the setup hook double-fire is the most impactful finding. Fixing Priority 1 alone saves more tokens per conversation than all the static prompt trimming combined.
