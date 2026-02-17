# fd-consumer-experience: Token Efficiency from the Consumer's Perspective

**Reviewer**: fd-consumer-experience
**Date**: 2026-02-12
**Scope**: MCP tool output analysis, plugin overhead, skill/command bloat, double-delivery

---

## Executive Summary

tldr-swinton's core analysis engines are well-optimized (ultracompact format, path dictionaries, budget-aware truncation). However, the delivery layer -- MCP wrappers, hooks, skills, and plugin infrastructure -- adds measurable token waste that Claude Code pays for on every invocation. The largest issues are: (1) the `extract` tool returns ~6400 tokens of JSON that Claude rarely needs in full, (2) the `impact` tool returns redundant structural metadata, (3) the PostToolUse:Read hook can double-deliver information already provided by the session-start skill, and (4) stale documentation in AGENTS.md references three retired skills that no longer exist.

**Total estimated waste per typical session**: 2,000-5,000 tokens of avoidable overhead.

---

## 1. MCP Tool Output Analysis

### 1.1 `context` tool (mcp_server.py:202-253)

**What it returns**: Ultracompact formatted text string via `format_context_pack()`.

**Strengths**:
- Path dictionary compression (`P0=path P1=path`) is excellent -- saves ~30% on repeated file references
- Budget-aware truncation with `... (budget reached)` markers
- Line number annotations are compact (`@256`)

**Waste found**: NONE significant. The ultracompact format (output_formats.py:725-810) is already one of the most token-efficient code representations available. The path dictionary, relevance tags (`[depth_0]`, `[contains_diff]`), and code fencing are all actionable by Claude Code.

**Sample output**: 401 tokens for 14 functions at depth 2. This is well-optimized.

### 1.2 `diff_context` tool (mcp_server.py:562-644)

**What it returns**: Ultracompact formatted string with diff-mapped symbols.

**Strengths**:
- Preset system (presets.py:12-33) collapses 6+ flags into one word -- good UX
- Import compression (`## Common Imports` header + per-file unique imports) avoids repeating shared imports
- Code bodies only shown for diff-containing symbols; callers/callees get signatures only

**Waste found**:
- **Minor**: The `## Diff Context: <base>...<head>` header (output_formats.py:731-733) includes full 40-char SHA hashes. Claude Code never uses the full SHA. Truncating to 8 chars would save ~64 chars per invocation.
  - Estimated waste: ~16 tokens per call
- **Minor**: Blank lines between every symbol entry (output_formats.py:800) add up. For a 20-symbol diff, that is 20 blank lines = ~20 tokens.
  - These serve as visual separators and are arguably useful for parsing, so this is debatable.

**Overall**: diff_context is well-designed. The compact preset (2000 token budget) is appropriate.

### 1.3 `distill` tool (mcp_server.py:699-735)

**What it returns**: Prescriptive markdown with 4 sections (Files to Edit, Key Functions, Dependencies, Risk Areas, Summary).

**Strengths**:
- Budget-aware progressive trimming (distill_formatter.py:156-167) is smart -- sheds risk areas first, then dependencies, then key functions
- Structured output is directly actionable

**Waste found**:
- **Medium**: The "Key Functions" section (distill_formatter.py:115-124) includes full file paths in call targets. For a 14-function distill, calls like `src/tldr_swinton/modules/core/output_formats.py:_contextpack_to_dict` repeat the same long path prefix. This section alone was 750 tokens in testing.
  - **Recommendation**: Apply the same path dictionary compression used in ultracompact format. Would save ~200 tokens on a typical distill.
- **Medium**: When no dependencies or risk areas are found, the output still renders `## Dependencies (will break if changed)\n- None\n\n## Risk Areas\n- None` (8 lines, ~20 tokens). These empty sections are noise for Claude Code.
  - **Recommendation**: Omit sections with no content. Save ~20-40 tokens per empty section.
- **Bug found**: The `delegate` CLI mode (`tldrs context <symbol> --delegate "task"`) appears to double-render the distill output. Observed in testing: the same "## Files to Edit ... ## Summary" block was printed twice. This is a 100% token waste duplication.

### 1.4 `structural_search` tool (mcp_server.py:647-696)

**What it returns**: Dict with `pattern`, `language`, and `matches` list. Each match has `file`, `line`, `end_line`, `text`, `meta_vars`.

**Strengths**:
- Match text is included inline, so Claude doesn't need a follow-up Read
- meta_vars extraction is useful for pattern-based refactoring

**Waste found**:
- **Minor**: The `meta_vars` dict is included even when empty (`{}`). For patterns like `$OBJ.$METHOD($$$ARGS)`, meta_vars can contain useful bindings, but for simpler patterns they're always empty.
  - Estimated waste: `"meta_vars":{}` * N matches = ~15 chars * 50 = 750 chars (~188 tokens at max_results)
  - **Recommendation**: Omit `meta_vars` key when empty.
- **Minor**: The `end_line` field is often `line + 1` for single-line matches. Could be omitted when `end_line == line`.
  - Estimated waste: ~10 chars * 50 = 500 chars (~125 tokens at max_results)

### 1.5 `extract` tool (mcp_server.py:186-197)

**What it returns**: Full JSON dict from `api.extract_file()` with `file_path`, `language`, `docstring`, `imports`, `classes`, `functions`, `call_graph`.

**THIS IS THE BIGGEST TOKEN WASTE IN THE ENTIRE PLUGIN.**

**Analysis**: For `mcp_server.py` (a 795-line file), extract returns **25,627 bytes (~6,400 tokens)**. The file itself is ~795 lines. So extract returns roughly 80% of the file's token count as metadata.

Breakdown:
- `functions` array: 17,092 chars (4,273 tokens) -- 30 function entries with full details
- `call_graph`: 1,597 chars (399 tokens) -- who calls whom (within the file)
- `imports`: 382 chars (95 tokens)
- `classes`: 458 chars (114 tokens)
- `docstring`: 252 chars (63 tokens) -- the module docstring
- `file_path` + `language`: 53 chars (13 tokens)

**Per-function overhead** in the functions array:
- Each function entry includes `is_async: false` and `decorators: []` even when not async and not decorated. Across 30 functions: ~693 chars (173 tokens) of null/false/empty fields.
- Each function includes full `params` array AND a `signature` string that contains the same params. The params array is redundant when signature is present.
  - For 30 functions with avg 2 params: ~600 chars (150 tokens) of redundant parameter data

**The PostToolUse:Read hook delivers this extract for every code file >300 lines.** For a typical session where Claude reads 5 large files, that is ~32,000 tokens of extract data injected into context. Claude Code almost never needs the full call_graph or per-function param arrays -- it just needs signatures and line numbers.

**Recommendations**:
1. Create a "compact extract" format that returns only: function signatures with line numbers, class names with method signatures, and import summary. Estimated size: ~800 tokens for the same file (87% reduction).
2. Omit `is_async: false`, empty `decorators`, empty `docstring`, redundant `params` array.
3. Omit `call_graph` by default; make it opt-in with a flag.
4. The PostToolUse:Read hook should use this compact format.

### 1.6 `impact` tool (mcp_server.py:335-345)

**What it returns**: JSON dict with nested caller tree.

**Analysis**: For `format_context_pack` (30 callers, 8 nested), returns 9,242 bytes (~2,310 tokens).

**Waste found**:
- **`truncated: false`** on every caller node (including 30 top-level + 8 nested = 38 nodes): ~684 chars (171 tokens). This field is only meaningful when `true`; omit when false.
- **`callers: []`** on 24 leaf nodes: ~288 chars (72 tokens). Empty arrays should be omitted.
- **`caller_count: 0`** on 24 leaf nodes: ~384 chars (96 tokens). Redundant -- derivable from `callers.length`.
- **`caller_count`** on all nodes: redundant with `callers` array length. Always derivable.
  - Total redundant fields: ~1,561 chars (390 tokens) -- **17% of the total output**.

**Recommendation**: Strip `truncated` when false, `callers` when empty, `caller_count` always (it's derivable). For the pre-serena-edit hook (which runs this), these savings matter because the hook adds this to `additionalContext` which goes into Claude's working context.

### 1.7 Daemon wrapper overhead (mcp_server.py:90-119)

All daemon-proxied tools (tree, structure, search, extract, cfg, dfg, slice, impact, dead, arch, calls, imports, importers, semantic, diagnostics, change_impact, status) pass through `_send_command()` which returns the daemon's JSON response verbatim. The daemon wraps every response in `{"status": "ok", "result": ...}` (daemon.py:41-45). The MCP tool functions then return this dict directly to Claude Code.

This means Claude Code receives `{"status": "ok", "result": { ... actual data ... }}` for every daemon call. The `"status": "ok"` wrapper is 16 chars of overhead per call -- trivial individually but adds up across a session.

**Recommendation**: Unwrap the daemon response in MCP tool functions. Return only the `result` value. If status is not "ok", return an error string.

---

## 2. Plugin Overhead

### 2.1 Setup Hook (hooks/setup.sh)

**What it injects**: Project summary (file count, changed count, semantic index status) + either diff-context output or structure output + "Available presets" line.

**Size**: ~292 bytes on a clean repo (with structure fallback returning empty), up to ~5,600 bytes (setup summary + diff-context compact output) on a repo with changes.

**Strengths**:
- Fallback chain (diff-context -> structure -> static tip) is robust
- Prebuild cache warming in background is smart (`tldrs prebuild --project . &`)
- 10-second timeout is appropriate

**Waste found**:
- **Line 84**: `echo "Available presets: compact, minimal, multi-turn"` -- This is 51 chars (~13 tokens) injected into every session. Claude Code already has this information from the command definitions and skill instructions. Redundant.
- **Lines 66-67**: When the structure command returns `{"root": "src", "language": "python", "files": []}` (empty), it is pure noise. The JSON structure wrapper for an empty result is 43 chars of zero information.
- **Lines 17-19**: The ast-grep unavailability warning (`tldrs: Structural search unavailable...`) fires on every session where ast-grep-py is not installed. If this is a known permanent state, it wastes ~82 chars per session.

**Overall**: The setup hook is reasonably sized. Total overhead: ~150 tokens worst case on a clean repo. Acceptable.

### 2.2 PostToolUse:Read Hook (hooks/post-read-extract.sh)

**What it injects**: `tldrs extract` output wrapped in `additionalContext` JSON for every code file >300 lines read during the session (once per file per session, flagged).

**Size**: ~6,400 tokens per large Python file (see extract analysis above).

**Strengths**:
- Per-file flagging prevents re-extraction (line 41-43)
- 300-line threshold filters out small files
- Non-code file exclusion (line 21-25) is comprehensive

**Waste found**:
- **CRITICAL**: This is the single largest source of token waste in the plugin. For a session where Claude reads 5 large files (common during feature work), the hook injects ~32,000 tokens of extract data into context. Much of this data is never used by Claude -- it just needs signatures and line numbers to know where things are.
- **The hook message format** (line 57-63) wraps the entire extract JSON in a string: `tldrs extract output for {file_path} ({line_count} lines):\n{extract}`. This means the JSON is embedded as a string inside JSON, losing any structural benefit.
- **No deduplication with session-start**: If the session-start skill already ran diff-context (which includes signatures for changed files), and Claude then reads those same files, the hook delivers redundant signatures for symbols already in context.

**Recommendations**:
1. Use a compact extract format (signatures + line numbers only, no call_graph, no redundant params)
2. Skip files whose paths appear in the session-start diff-context output (check flag files)
3. Consider raising the threshold to 500 lines -- files under 500 lines are cheap for Claude to scan directly

### 2.3 PreToolUse Hooks for Serena (hooks/pre-serena-edit.sh)

**What it injects**: `tldrs impact` output for the symbol being edited, wrapped in `additionalContext`.

**Size**: ~2,300 tokens for a well-connected symbol (30 callers).

**Waste found**:
- Same redundant fields as the impact tool analysis (390 tokens of `truncated: false`, `callers: []`, `caller_count: 0`)
- The wrapper message (line 56-63) includes `Review callers above before proceeding. Update callers if the change breaks their assumptions.` -- 93 chars of instruction. This instruction is reasonable for the first time but is repeated per-symbol (even though Claude already knows to check callers).

**Overall**: This hook provides genuine value (preventing breaking callers). The overhead is moderate and justified.

---

## 3. Skill Instruction Bloat

### 3.1 tldrs-session-start (75 lines, 2,147 bytes, ~537 tokens)

**Assessment**: Well-structured. The decision tree format is efficient and actionable. The "When to Skip" section (lines 68-72) is valuable -- it tells Claude when NOT to use the tool, saving future invocations.

**Minor waste**:
- Lines 48-52 (subagent distill section) is 5 lines (~50 tokens) that only applies when spawning subagents. This is a rare case that could be documented elsewhere.
- Line 65: "Always use `--preset compact` unless you have a reason not to" -- redundant with the decision tree above it.

### 3.2 tldrs-map-codebase (54 lines, 1,583 bytes, ~396 tokens)

**Assessment**: Concise and well-scoped. Good use of "When to Skip" section.

**No significant waste found.** This is a model of how skill instructions should be written.

### 3.3 tldrs-interbench-sync (112 lines, 3,330 bytes, ~832 tokens)

**Assessment**: This skill has the most detailed instructions because it orchestrates edits across 4 files in a separate repo. The detail is justified.

**Waste found**:
- **Lines 43-82**: The pattern examples for each interbench file (regression_suite.json, ab_formats.py, demo-tldrs.sh, score_tokens.py) consume ~40 lines (~350 tokens). These are essential for correctness -- the patterns must be followed exactly. However, this skill is invoked rarely (only after adding new tldrs capabilities), so the per-session cost is zero unless explicitly triggered.

**Overall**: No changes needed. This skill is appropriately detailed for its complexity.

### 3.4 Total skill overhead

All 3 skills: **7,060 bytes (~1,765 tokens)** loaded into Claude Code's skill registry.

Claude Code loads skill descriptions (the YAML front matter) into context at session start. The full SKILL.md body is only loaded when the skill is invoked. So the per-session overhead is:
- session-start description: ~50 tokens (long description, line 3)
- map-codebase description: ~40 tokens
- interbench-sync description: ~25 tokens
- **Total per-session skill description overhead: ~115 tokens**

This is acceptable.

---

## 4. Command Template Overhead

### 4.1 Command files total: 5,084 bytes (~1,271 tokens)

| Command | Bytes | Est. Tokens | Assessment |
|---------|-------|-------------|------------|
| find.md | 693 | 173 | Includes "Tips" section with 3 bullets. Lean. |
| quickstart.md | 364 | 91 | Minimal -- just invokes `tldrs quickstart`. Good. |
| structural.md | 994 | 249 | Pattern syntax + 3 examples. Justified for unfamiliar syntax. |
| extract.md | 702 | 176 | "When to use" + "Tips". Appropriate. |
| context.md | 1,237 | 309 | Includes `--delegate` docs. Slightly long but justified. |
| diff-context.md | 1,094 | 274 | Multi-flag template with tips. Appropriate. |

**Waste found**:
- Command descriptions (YAML front matter) are loaded at session start. Total front matter across 6 commands: ~600 bytes (~150 tokens).
- The `context.md` command (line 22) embeds a complex bash template with multiple conditional expansions: `tldrs context "$ARGUMENTS.symbol" --project . --depth ${ARGUMENTS.depth:-2} --budget ${ARGUMENTS.budget:-2000} --format ultracompact ${ARGUMENTS.delegate:+--delegate "$ARGUMENTS.delegate"}`. This is 170 chars of template that Claude needs to parse. Acceptable given the number of optional parameters.

**Overall**: Command templates are well-sized. No significant reduction opportunities.

---

## 5. Double-Delivery Problem

### 5.1 Session-Start + PostToolUse:Read Overlap

**Scenario**: Claude starts a session. The session-start skill runs `tldrs diff-context --preset compact`, which outputs signatures and code for changed files. Claude then reads one of those changed files. The PostToolUse:Read hook fires and runs `tldrs extract` on that file, adding ~6,400 tokens of metadata for a file whose signatures are already in context from diff-context.

**Analysis**:
- The diff-context output contains: symbol signatures, line ranges, relevance labels, and code bodies for changed symbols.
- The extract output contains: all function signatures (including unchanged ones), all imports, class hierarchies, and call graph.
- **Overlap**: Function signatures for changed symbols are delivered twice. The diff-context version includes code bodies; the extract version includes params arrays and docstrings.
- **Unique in extract**: Unchanged function signatures, full import list, call graph, class hierarchy.

**Estimated double-delivery**: For a file with 30 functions where 5 are changed, ~5 signatures are delivered twice = ~250 tokens of pure duplication. The other ~6,150 tokens from extract are technically new information, but most of it (call_graph, redundant params, empty decorators) is not actionable.

### 5.2 Setup Hook + Session-Start Skill Overlap

**Scenario**: The setup hook (SessionStart) runs and may produce diff-context output (setup.sh:55). Then Claude triggers the session-start skill, which also runs diff-context.

**Analysis**: This is a real double-delivery. If there are changes in the repo:
1. Setup hook runs `tldrs diff-context --project . --preset compact` (line 55)
2. Session-start skill tells Claude to run `tldrs diff-context --project . --preset compact`

**Both produce identical output.** This is ~1,333 tokens (5,333 bytes) delivered twice = **~1,333 tokens wasted**.

**Root cause**: The setup hook was designed as a standalone briefing, but then the session-start skill was added as an autonomous skill that does the same thing. They don't coordinate.

**Recommendation**: Either:
- (A) Remove diff-context from the setup hook; let it only provide the project summary (file count, index status, changed files list). Let the session-start skill handle the actual diff-context.
- (B) Have the setup hook set a flag file when it runs diff-context, and have the session-start skill check for that flag and skip if already done.
- Option (A) is cleaner and saves ~1,333 tokens per session.

---

## 6. Stale Documentation Overhead

### 6.1 AGENTS.md references 3 retired skills

AGENTS.md lines 90-92 reference `tldrs-find-code`, `tldrs-understand-symbol`, and `tldrs-explore-file`. These skills were retired (per CLAUDE.md and MEMORY.md -- "Retired: find-code, explore-file, understand-symbol (MCP `tldr-code` tools replace them)").

While this doesn't directly waste tokens in tool output, if Claude Code reads AGENTS.md (which it does for project context), these 3 lines create confusion about available capabilities and may cause Claude to attempt to invoke skills that don't exist.

### 6.2 AGENTS.md hooks description is stale

AGENTS.md line 97 says: `PreToolUse` on **Read** and **Grep**: Suggests running tldrs recon before reading files (once per session via flag file)

But the actual hooks.json shows:
- PreToolUse hooks are on `mcp__plugin_serena_serena__replace_symbol_body` and `mcp__plugin_serena_serena__rename_symbol` (Serena operations)
- PostToolUse hook is on `Read`
- There is no PreToolUse hook on Read or Grep

This stale description costs ~40 tokens but, more importantly, gives Claude Code incorrect expectations about when hooks fire.

---

## 7. Prioritized Recommendations

### High Impact (>1,000 tokens saved per session)

| # | Issue | Location | Est. Savings | Effort |
|---|-------|----------|-------------|--------|
| 1 | **Create compact extract format** for PostToolUse:Read hook | hooks/post-read-extract.sh, api.py | ~25,000 tokens/session (5 files) | Medium |
| 2 | **Remove diff-context from setup hook** (let session-start handle it) | hooks/setup.sh:53-59 | ~1,333 tokens/session | Low |
| 3 | **Strip redundant fields from impact output** | daemon.py or MCP wrapper | ~390 tokens per impact call | Low |

### Medium Impact (200-1,000 tokens saved)

| # | Issue | Location | Est. Savings | Effort |
|---|-------|----------|-------------|--------|
| 4 | **Omit empty sections in distill output** | distill_formatter.py:100-153 | ~20-60 tokens/call | Low |
| 5 | **Apply path compression to distill calls list** | distill_formatter.py:115-124 | ~200 tokens/call | Medium |
| 6 | **Omit empty meta_vars in structural_search** | mcp_server.py:683-696 | ~188 tokens at max_results | Low |
| 7 | **Fix delegate double-render bug** | cli.py or context_delegation.py | 100% duplication | Low |

### Low Impact (<200 tokens saved, or correctness fixes)

| # | Issue | Location | Est. Savings | Effort |
|---|-------|----------|-------------|--------|
| 8 | **Update AGENTS.md** -- remove 3 retired skills, fix hooks description | AGENTS.md:90-92, 97 | Correctness | Low |
| 9 | **Truncate SHA hashes** in diff context header | output_formats.py:731-733 | ~16 tokens/call | Low |
| 10 | **Remove "Available presets" line from setup hook** | hooks/setup.sh:84 | ~13 tokens/session | Trivial |
| 11 | **Unwrap daemon `{"status":"ok","result":...}`** in MCP layer | mcp_server.py (all daemon tools) | ~4 tokens/call | Low |

---

## 8. File Reference

| File | Path | Role |
|------|------|------|
| MCP Server | `src/tldr_swinton/modules/core/mcp_server.py` | Tool definitions, daemon proxy, direct-call tools |
| Output Formats | `src/tldr_swinton/modules/core/output_formats.py` | All format renderers (ultracompact, cache-friendly, JSON, etc.) |
| Distill Formatter | `src/tldr_swinton/modules/core/distill_formatter.py` | Prescriptive summary format |
| Presets | `src/tldr_swinton/presets.py` | CLI flag presets (compact, minimal, multi-turn) |
| Daemon | `src/tldr_swinton/modules/core/daemon.py` | Socket-based daemon with cached queries |
| Context Delegation | `src/tldr_swinton/modules/core/context_delegation.py` | Retrieval plan generation |
| Astgrep Engine | `src/tldr_swinton/modules/core/engines/astgrep.py` | Structural search |
| DiffLens Engine | `src/tldr_swinton/modules/core/engines/difflens.py` | Diff-focused context |
| Setup Hook | `.claude-plugin/hooks/setup.sh` | Session start briefing |
| PostToolUse Hook | `.claude-plugin/hooks/post-read-extract.sh` | Auto-extract on file read |
| PreToolUse Hook | `.claude-plugin/hooks/pre-serena-edit.sh` | Caller analysis before Serena edits |
| Hooks Config | `.claude-plugin/hooks/hooks.json` | Hook definitions and matchers |
| Plugin Manifest | `.claude-plugin/plugin.json` | Plugin metadata, MCP server config |
| Session-Start Skill | `.claude-plugin/skills/tldrs-session-start/SKILL.md` | Diff-first workflow instructions |
| Map-Codebase Skill | `.claude-plugin/skills/tldrs-map-codebase/SKILL.md` | Architecture exploration instructions |
| interbench-Sync Skill | `.claude-plugin/skills/tldrs-interbench-sync/SKILL.md` | Eval coverage sync instructions |
| Commands | `.claude-plugin/commands/*.md` | 6 slash command templates |
| AGENTS.md | `AGENTS.md` | Shared agent documentation (has stale entries) |
