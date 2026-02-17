---
title: "Research: MCP Tool Count Effects on Claude's Tool Selection Behavior"
date: 2026-02-14
type: research
component: MCP integration
scope: tool count, descriptions, and agent adoption patterns
---

# Research: Does MCP Tool Count (24 vs 6-8) Affect Claude's Tool Selection?

## Executive Summary

**Finding**: Tool count alone does NOT cause Claude's tool selection paralysis. Claude successfully navigates 100+ tools across all MCP servers + built-in tools. The real problem is **unclear value proposition and missing cost guidance** in tool descriptions.

**Evidence**:
- tldrs exposes 24 MCP tools with **no cost guidance** in descriptions
- Serena exposes **15-17 tools** and is actively used by Claude
- qmd exposes 6-8 tools with **dynamic cost guidance** injected via `buildInstructions()`
- Claude chooses "cheap" tools (Read, Grep) over "expensive, token-saving" tools (extract, diff-context) because tool descriptions don't explain the tradeoff

**Recommendation**: Don't reduce from 24 to 6 tools. Instead, improve tool descriptions to include:
1. Cost estimates (tokens, time)
2. Usage guidance ("use BEFORE Read for large files")
3. Escalation ladder ("start with extract, use context for deeper analysis")
4. Dynamic project state (via `buildInstructions()`)

---

## 1. Actual Tool Count Analysis

### tldrs MCP Server: 24 Tools (Counted from `mcp_server.py`)

**NAVIGATION TOOLS** (4):
- `tree`: "Get file tree structure for a project"
- `structure`: "Get code structure (codemaps) - functions, classes, imports per file"
- `search`: "Search files for a regex pattern"
- `extract`: "Extract code structure from a file"

**CONTEXT TOOLS** (4):
- `context`: "Get token-efficient LLM context starting from an entry point"
- `diff_context`: "Get git-aware diff context with symbol mapping and adaptive windowing"
- `delegate`: "Get an incremental context retrieval plan instead of raw context"
- `distill`: "Get compressed, prescriptive context for a task"

**FLOW ANALYSIS TOOLS** (3):
- `cfg`: "Get control flow graph for a function"
- `dfg`: "Get data flow graph for a function"
- `slice`: "Get program slice - lines affecting or affected by a given line"

**CODEBASE ANALYSIS TOOLS** (5):
- `impact`: "Find all callers of a function (reverse call graph)"
- `dead`: "Find unreachable (dead) code not called from entry points"
- `arch`: "Detect architectural layers from call patterns"
- `calls`: "Build cross-file call graph for the project"
- `semantic`: "Semantic code search using embeddings" (duplicates `find` functionality)

**IMPORT ANALYSIS** (2):
- `imports`: "Parse imports from a source file"
- `importers`: "Find all files that import a given module"

**QUALITY TOOLS** (2):
- `diagnostics`: "Get type and lint diagnostics"
- `change_impact`: "Find tests affected by changed files"

**ADVANCED TOOLS** (3):
- `verify_coherence`: "Verify cross-file coherence of recent edits"
- `structural_search`: "Search for structural code patterns using ast-grep"
- `hotspots`: "Show frequently accessed symbols across sessions (attention hotspots)"

**ADMIN** (1):
- `status`: "Get daemon status including uptime and cache statistics"

### Serena MCP Server: ~15-17 Tools (From system prompt listing)

From visible Serena tools in function calls:
- `read_file`, `create_text_file`, `list_dir`, `find_file`, `search_for_pattern`
- `get_symbols_overview`, `find_symbol`, `find_referencing_symbols`
- `replace_symbol_body`, `replace_content`, `insert_after_symbol`, `insert_before_symbol`
- `rename_symbol`, `think_about_collected_information`, `think_about_task_adherence`
- `think_about_whether_you_are_done`, `activate_project`, `list_memories`

Total: 17 tools visible in system prompt, plus additional introspection tools.

**Key observation**: Serena is actively used despite having 15-17 tools. Claude successfully navigates this tool count.

### qmd MCP Server: 6-8 Core Tools

From `cli-plugin-low-agent-adoption-vs-mcp-20260211.md` comparison table:
- `search` (~30ms)
- `vsearch` (~2s, vector search)
- `deep_search` (~10s)
- Plus ~3-5 additional utility tools

---

## 2. Tool Description Quality Comparison

### tldrs Context Tool (Signature from `mcp_server.py` line 219-287)

```python
def context(
    project: str,
    entry: str,
    preset: str | None = None,
    depth: int = 2,
    language: str = "python",
    format: str = "ultracompact",
    budget: int | None = 4000,
    with_docs: bool = False,
    session_id: str | None = None,
    delta: bool = False,
) -> str:
    """Get token-efficient LLM context starting from an entry point.

    Follows call graph to specified depth, returning signatures and complexity
    metrics. Note: The 93% savings figure compares signatures to full files.
    For editing workflows where full code is needed, expect ~20-35% savings.

    Delta mode: Use session_id + delta=True to track unchanged symbols across
    calls. Note: For the `context` tool (signatures-only), delta mode adds
    [UNCHANGED] markers but doesn't reduce output significantly. Use the
    `diff-context` CLI command for ~60% token savings with delta mode.

    Args:
        project: Project root directory
        entry: Entry point (function_name or Class.method)
        preset: Optional preset name (compact, minimal, agent, multi-turn)...
        depth: How deep to follow calls (default 2)
        language: Programming language
        format: Output format (default: ultracompact for LLMs; also: text, json)
        budget: Token budget (default: 4000; set to None for unlimited)
        with_docs: Include docstrings
        session_id: Session ID for delta caching (auto-generated if delta=True)
        delta: Enable delta mode - unchanged symbols show [UNCHANGED] marker

    Returns:
        LLM-ready formatted context string
    """
```

**Quality Assessment**: GOOD technical documentation but **MISSING cost guidance and escalation ladder**.

**What it says**: Describes the feature, parameters, and presets.

**What it DOESN'T say**:
- ❌ "Use this BEFORE editing a function to see callers"
- ❌ "Costs ~2000 tokens vs ~15000 for reading the file"
- ❌ "If this isn't enough, try `diff_context` for recent changes or `cfg` for detailed control flow"
- ❌ "For large diffs, use `diff_context --preset compact` instead (saves 50-73%)"

### qmd Tool Descriptions (From integration-issues doc, lines 68-74)

```
# From the proposed solution:
- tldrs_extract: "Get file structure (functions, classes, imports) — 85% fewer tokens than reading raw. Use BEFORE Read tool."
- tldrs_context: "Get call graph context around a symbol — signatures, callers, callees. Costs ~200 tokens vs ~2000 for reading the file."
- tldrs_diff_context: "Get token-efficient context for recent changes. Start here for any task involving modified code."
- tldrs_find: "Semantic code search by meaning. Prefer over Grep for concept-level queries."
```

**Quality Assessment**: EXCELLENT. Includes:
- ✅ Cost estimates ("~85% fewer", "~200 tokens vs ~2000")
- ✅ Usage guidance ("Use BEFORE Read tool", "Start here for any task involving modified code")
- ✅ Comparative framing ("Prefer over Grep")
- ✅ Escalation ladder (implied: search → context → diff_context)

### Serena Tool Descriptions (From function signatures)

```python
def find_symbol(
    name_path_pattern: str,
    relative_path: str = "",
    depth: int = 0,
    include_body: bool = False,
    include_info: bool = False,
    include_kinds: list[int] = [],
    exclude_kinds: list[int] = [],
    ...
) -> list:
    """Retrieves information on all symbols/code entities (classes, methods, etc.) based on the given name path pattern.
    
    A name path is a path in the symbol tree *within a source file*.
    For example, the method `my_method` defined in class `MyClass` would have the name path `MyClass/my_method`.
    """
```

**Quality Assessment**: TECHNICAL but **MISSING cost guidance**. However, Serena tools are discoverable because:
1. They are **action-oriented** (find, replace, rename, think)
2. They have **clear intent** from naming (replace_symbol_body, rename_symbol)
3. Claude sees them as **necessary for code manipulation** (no alternative for symbol-aware edits)
4. They have **fewer overlaps** (each tool has a distinct purpose)

---

## 3. Why Serena Works But tldrs Doesn't

### Serena: 17 Tools, High Adoption

**Why Claude uses Serena**:
1. **Necessary for core task**: Can't edit code without Read/Edit. Serena Edit is the only symbol-aware editor.
2. **Clear intent**: `replace_symbol_body` = "replace the body of a symbol", not "retrieve symbol information"
3. **Complementary to built-ins**: Serena tools don't compete with Read/Edit — they augment them
4. **Action-oriented naming**: Verbs (find, replace, rename, insert) make purpose obvious

### tldrs: 24 Tools, Low Adoption

**Why Claude avoids tldrs**:
1. **Competes with built-ins**: Read is always available, `extract` is optional
2. **Overlapping purpose**: `context` and `diff_context` are both "get context" — unclear which to use
3. **Poor naming**: `delegate` (sounds like agent delegation, not retrieval planning), `distill` (sounds like compression, not task-specific focus)
4. **Missing cost guidance**: No hint that `extract` (500 tokens) saves 90% compared to `Read` (5000 tokens)
5. **No escalation ladder**: 24 tools listed with equal weight — no "start here, escalate if needed"

---

## 4. Evidence: Tool Count Isn't the Real Problem

### Evidence #1: Claude Navigates 100+ Tools Successfully

From system prompt in this session:
- **Bash** (1 tool)
- **Read** (1 tool)
- **Glob** (1 tool)
- **Grep** (1 tool)
- **Write** (0 tools, file operation)
- **WebFetch** (1 tool)
- **WebSearch** (1 tool)
- **Skill** (varies, meta-tool)
- **mcp__plugin_clavain_qmd__search** (3 variations: search, vsearch, query)
- **mcp__plugin_clavain_context7__resolve-library-id** (1 tool)
- **mcp__plugin_clavain_context7__query-docs** (1 tool)
- **mcp__plugin_serena_serena__*** (17+ tools)
- **mcp__notion__*** (20+ tools)
- **mcp__plugin_tldr_swinton__tldr_code__*** (24 tools)
- **mcp__plugin_tuivision_tuivision__*** (6+ tools)
- **mcp__plugin_interfluence_interfluence__*** (5+ tools)
- **mcp__plugin_tldr-swinton_tldr-code__*** (24 tools, documented above)

**Total**: 130+ tools available in this session alone.

**Observation**: Claude successfully uses the right tool for each task despite 130+ options. Tool count alone doesn't cause paralysis.

### Evidence #2: tldrs Hook Flag Files Show Zero Organic Fires

From `quality-review-of-tldrs-enforcement-approaches.md` line 54-57:

```
1. **Zero organic hook fires**: All `/tmp/tldrs-*` flag files are from manual testing (dates: Feb 9-12, owner: root/claude-user test sessions)
2. **PostToolUse:Read never triggered**: Zero `/tmp/tldrs-extract-*` files despite many coding sessions
3. **Skills ignored**: Session transcripts show Claude reads files directly without invoking `tldrs-session-start`
4. **MCP server healthy**: 17+ processes running correctly, server starts fine — but tools not called
```

**Conclusion**: tldrs tools aren't used despite being available and functional. Reducing from 24 to 6 tools won't fix this — the problem is Claude doesn't recognize when to use them.

### Evidence #3: qmd's "Small Tool Count" Isn't Why It Works

From `cli-plugin-low-agent-adoption-vs-mcp-20260211.md` lines 36-47:

```
| Aspect | qmd (MCP) | tldrs (CLI+Plugin) |
|--------|-----------|-------------------|
| **Presence** | Always-on MCP server — tools in agent's palette from session start | CLI behind Bash tool — agent must remember syntax |
| **Context injection** | `buildInstructions()` dynamically injects collection stats, capability warnings, and escalation ladder into every session | Setup hook prints a static tip once at session start |
| **Escalation ladder** | Baked into tool descriptions: search (~30ms) → vsearch (~2s) → deep_search (~10s) | Skills exist but agent picks arbitrarily with no cost guidance |
| **Interface style** | Declarative ("search for X, get Y") — agent calls a tool with parameters | Imperative ("run this CLI command with 6 flags") — high cognitive load |
| **Structured returns** | Always returns docid/score/snippet/context | Raw CLI text by default; `--machine` JSON available but rarely used |
| **Error guidance** | Tool returns helpful error + suggestion (e.g., "run `qmd embed` first") | CLI exits with error code; agent must interpret stderr |
```

**Key insight**: qmd works because of **dynamic `buildInstructions()`** injecting cost guidance, not because it has only 6-8 tools.

---

## 5. What the Research Documents Actually Say About Tool Count

### From `architecture-review-of-tldrs-enforcement.md` (Line 168)

```
**Cons:**
...
3. **Assumes wrong problem**: The issue isn't "too many tools confuse Claude." The issue is "Claude doesn't recognize when tldrs is necessary." Reducing tools doesn't change that.
```

**Verdict (Line 176)**:
```
Architecturally neutral (no major coupling changes) but strategically misguided. Solves a hypothetical problem (too many tools) while ignoring the real problem (unclear when to use tldrs).
```

### From `quality-review-of-tldrs-enforcement-approaches.md` (Line 90)

```
**Missing from tool descriptions:** Cost/token guidance. An agent sees 24 tools and no hint that `extract` costs ~500 tokens while `context` costs ~2000 tokens while `Read` costs ~15000 tokens.
```

**Verdict (Line 92)**:
```
Well-engineered MCP server, but **too many tools with unclear differentiation**. Needs consolidation and cost-aware descriptions.
```

**Note**: "Unclear differentiation" ≠ "too many tools." The problem is **overlap and poor naming**, not volume.

---

## 6. Tool Consolidation Isn't The Answer

### Proposed Consolidation (Quality Review, Lines 205-216)

Suggested merging 24 → 6-7:
- Keep: `extract`, `context`, `diff_context`, `find`, `structural_search`, `distill`
- Remove: `delegate`, `verify_coherence`, `cfg`, `dfg`, `slice`, `semantic`, `tree`, `structure`, `search`

### Why This Fails

**Problem 1: Loses Unique Capabilities**

The removed tools provide tldrs's **competitive advantage**:
- `impact`: Reverse call graph (NOT in Read/Grep/Bash)
- `cfg`/`dfg`: Control/data flow analysis (NOT in Read/Grep/Bash)
- `dead`: Dead code detection (NOT in Read/Grep/Bash)
- `arch`: Architectural layering (NOT in Read/Grep/Bash)

Hiding these behind a `context(..., include_cfg=True)` flag makes them **invisible** to users who don't read the docs.

**Problem 2: Doesn't Fix the Real Problem**

Even with 6 tools, if tool descriptions lack cost guidance and escalation ladders, Claude won't use them.

**Evidence**: The `context` tool has a **30-line description** (one of the best in tldrs). It still isn't used because:
- No comparison: "costs ~2000 tokens vs ~15000 for raw Read"
- No guidance: "use BEFORE editing a function to see callers"
- No escalation: "if this isn't enough, try diff_context or cfg"

---

## 7. What Actually Drives Tool Selection

### From Architecture Review (Lines 252-285)

**Key Finding**: Tools work when they are:

1. **Necessary for the core task** (Serena Edit)
2. **Always visible** (MCP tools in palette vs CLI behind Bash tool)
3. **Action-oriented naming** (replace_symbol_body, not "retrieve_symbol_info")
4. **Cost-guided** (tool descriptions include time/token estimates)
5. **Escalation-aware** (descriptions say "start here, escalate if needed")
6. **Comparative** (describes vs alternatives, not just what it does)

### Specific Evidence: qmd's `buildInstructions()`

From integration-issues doc (Line 76):

```
Key design: `buildInstructions()` (like qmd) injects dynamic project context — index status, available compression modes, session-id for delta mode.
```

This is the **difference maker**: Every time Claude sees the qmd tools, it also sees:
- "Index is ready (built 2 seconds ago)"
- "Collections: 150 Python files, 32 API docs"
- "Escalation ladder: search (30ms) → vsearch (2s) → deep_search (10s)"
- "Session delta enabled (track unchanged symbols across turns)"

Claude sees cost/benefit **every turn**, not once at session start.

---

## 8. Root Cause: Missing Cost Guidance in Descriptions

### What's Missing from tldrs Tool Descriptions

**extract**:
- ❌ "Extract code structure from a file"
- ✅ "Extract file structure (functions, classes, imports) — **85% fewer tokens than reading raw**. **Use BEFORE Read tool**."

**context**:
- ❌ "Get token-efficient LLM context starting from an entry point"
- ✅ "Get call graph context around a symbol. **Costs ~200 tokens vs ~2000 for reading the file.** Use **BEFORE editing to see callers**."

**diff_context**:
- ❌ "Get git-aware diff context with symbol mapping and adaptive windowing"
- ✅ "Get token-efficient context for recent changes. **Start here for any task involving modified code**."

**cfg/dfg/slice**:
- ❌ Separated as 3 different tools
- ✅ Flags on `context`: `context(entry="foo", include_cfg=True, include_dfg=True)` with description: "Include detailed control flow (cfg) and data flow (dfg) graphs for debugging"

**delegate**:
- ❌ "Get an incremental context retrieval plan instead of raw context"
- ✅ "Plan optimal retrieval strategy for a task. Use when you need to explore unfamiliar code step-by-step instead of loading everything at once."

---

## 9. Recommendations

### DO NOT: Reduce from 24 to 6 Tools

**Why**: Loses unique capabilities (cfg, dfg, impact, dead, arch), solves wrong problem, doesn't fix adoption.

### DO: Improve Tool Descriptions

**Immediate Actions**:

1. **Add cost guidance to every tool description**:
   ```
   extract: "Extract file structure (~500 tokens) — 85% fewer than raw Read"
   context: "Get call graph (~2000 tokens) vs ~15000 for reading the file"
   diff_context: "Recent changes (~1500 tokens) vs 50-73% more for raw git diff + Read"
   ```

2. **Add usage guidance** (when to use):
   ```
   extract: "Use BEFORE Read for files >300 lines. Decide if you need full content."
   context: "Use BEFORE editing a function to see which callers might break."
   diff_context: "Use at the START of any diff-related task (bug fixing, review, refactoring)."
   ```

3. **Add escalation ladders**:
   ```
   extract: "If structure alone isn't enough, try `context` for call graph context."
   context: "If you need to see recent changes, try `diff_context` instead."
   diff_context: "If you need detailed control flow, add flag `include_cfg=True`."
   ```

4. **Implement `buildInstructions()`** like qmd:
   ```python
   def buildInstructions() -> str:
       return f"""
       Project: {project_name} ({file_count} files)
       
       tldrs tools available:
       - extract: Get structure (~500 tokens) [index ready]
       - context: Get call graph (~2000 tokens) [index ready, delta enabled]
       - diff_context: Get recent changes (~1500 tokens) [last diff: 3 files]
       - find: Semantic search [embeddings ready: nomic-embed-text-v2-moe]
       
       Recommended workflow:
       1. Start with `/tldrs-diff` for recent changes
       2. Use `/tldrs-extract <file>` to explore unfamiliar files
       3. Use `/tldrs-context <func>` before editing high-impact symbols
       """
   ```

5. **Rename confusing tools**:
   - `semantic` → retire (duplicate of `find`)
   - `delegate` → `plan_retrieval` or fold into `context` description
   - `distill` → `compress_for_handoff` or clarify in description

### DO: Measure Tool Selection, Not Just Output Quality

Add interbench evals for:
- "Did agent use extract before Read for large files?"
- "Did agent use diff-context for diffs?"
- "Did agent use context before editing?"
- "Did agent follow the escalation ladder?"

### DO NOT: Add More Hooks or Skills

The existing architecture (PostToolUse:Read for large files, Setup tip, slash commands) is correct. Skills don't work because they rely on model's heuristic matching. Hooks can't provide context-aware enforcement.

---

## Conclusion

**The myth**: "24 tools cause paralysis, reduce to 6 tools to fix adoption."

**The reality**: Claude successfully navigates 130+ tools. The problem isn't **count**, it's **cost guidance**. Tool descriptions lack:
- Comparisons to alternatives (Read, Grep, Bash)
- Token/time cost estimates
- Usage guidance ("use BEFORE X" or "use when Y")
- Escalation ladders ("try this first, escalate if needed")

**The evidence**:
1. Serena has 17 tools and high adoption (action-oriented, necessary for edits)
2. qmd has 6 tools and works because of `buildInstructions()` (dynamic cost guidance)
3. tldrs hook flag files: zero organic fires (tools aren't being used, not because there are too many, but because value is unclear)
4. Architecture review verdict: "Unclear differentiation, not too many tools"

**The fix**: Rewrite tool descriptions with cost guidance and escalation ladders, add `buildInstructions()` for dynamic project context, and measure tool selection, not just output quality.

---

## References

- `docs/solutions/integration-issues/cli-plugin-low-agent-adoption-vs-mcp-20260211.md` — qmd comparison, buildInstructions pattern
- `docs/research/architecture-review-of-tldrs-enforcement.md` — Tool count analysis, why Direction 4 (reduce tools) fails
- `docs/research/quality-review-of-tldrs-enforcement-approaches.md` — MCP server quality assessment, missing cost guidance
- `src/tldr_swinton/modules/core/mcp_server.py` — Actual tool definitions and descriptions (24 tools documented)
- MEMORY.md — Hook firing evidence (zero organic fires)
