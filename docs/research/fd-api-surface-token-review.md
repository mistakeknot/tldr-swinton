# fd-api-surface: Token Minimization API Review

**Reviewer**: fd-api-surface (flux-drive)
**Date**: 2026-02-12
**Scope**: MCP tool defaults, missing knobs, preset gaps, tool granularity, response format negotiation
**Files Reviewed**: `mcp_server.py`, `cli.py`, `presets.py`, `output_formats.py`, `contextpack_engine.py`, `difflens.py`, `block_compress.py`, `strip.py`, `type_pruner.py`, `import_compress.py`, `zoom.py`, `distill_formatter.py`, plugin commands (`context.md`, `diff-context.md`)

---

## Executive Summary

tldr-swinton has extensive token-saving machinery internally but **exposes less than half of it through the MCP API**. The CLI has 12+ compression-related flags; the MCP `context()` tool exposes 3 of them. The `diff_context()` MCP tool is better (delegates to presets), but still lacks critical knobs like `--zoom`, `--max-lines`, `--max-bytes`, `--compress`, `--strip-comments`, and `--compress-imports` as independent parameters. The net effect is that Claude Code calling through MCP gets suboptimal defaults and cannot request the same compression as the CLI. This is the single highest-impact finding.

**Severity ranking of findings:**

| # | Finding | Impact | Effort |
|---|---------|--------|--------|
| F1 | `context()` MCP defaults to `format="text"`, not `ultracompact` | HIGH | trivial |
| F2 | 6 CLI compression flags missing from MCP `context()` | HIGH | medium |
| F3 | `diff_context()` MCP lacks `zoom`, `max-lines`, `max-bytes`, individual flags | HIGH | medium |
| F4 | No Claude Code-optimized preset | MEDIUM | low |
| F5 | `strip_comments` not applied in `build_context_pack_delta()` | MEDIUM | low |
| F6 | No "already have" protocol beyond delta session IDs | LOW | high |
| F7 | `distill()` and `delegate()` lack `format` parameter for controlling verbosity | LOW | low |
| F8 | Plugin commands hardcode good defaults, but MCP tool schema does not | MEDIUM | low |

---

## Finding 1: `context()` MCP Tool Defaults Are Not Optimized for Claude Code

**Location**: `src/tldr_swinton/modules/core/mcp_server.py:202-253`

The MCP `context()` tool defaults to `format="text"`:

```python
@mcp.tool()
def context(
    ...
    format: str = "text",       # <-- Should be "ultracompact" for LLM consumers
    budget: int | None = None,  # <-- No default budget; unlimited output
    with_docs: bool = False,    # <-- Good default
    ...
```

**Problem**: Every AI tool calling `context()` without specifying format gets the verbose `text` format with emoji markers, full docstrings, and no path compression. The ultracompact format uses `P0=path` path IDs, strips whitespace, and is purpose-built for LLMs.

**Impact**: 30-50% more tokens than necessary on every `context()` call that does not explicitly set `format`.

**Contrast with plugin command**: The plugin command `context.md` (line 22) explicitly uses `--format ultracompact`:
```bash
tldrs context "$ARGUMENTS.symbol" --project . --depth ${ARGUMENTS.depth:-2} --budget ${ARGUMENTS.budget:-2000} --format ultracompact
```

But the MCP tool schema (which is what Claude Code sees when it has the `tldr-code` MCP server) has `format: str = "text"`.

**Recommendation**: Change MCP `context()` default to `format="ultracompact"` and `budget=2000`. The `text` format should only be used when a human is reading the output. Since the MCP server description explicitly says it's for "AI tools (OpenCode, Claude Desktop, Claude Code)", LLM-optimized defaults are correct.

**Risk**: Backward-compatible if MCP consumers relied on text format. Mitigated by the fact that MCP is relatively new and the description says "LLM-ready formatted context string."

---

## Finding 2: 6 CLI Compression Flags Missing from MCP `context()` Tool

**Location**: `src/tldr_swinton/modules/core/mcp_server.py:202-253` vs `src/tldr_swinton/cli.py:378-481`

The CLI `context` subcommand has these flags that the MCP `context()` tool lacks:

| CLI Flag | What it does | Token savings | MCP exposed? |
|----------|-------------|---------------|-------------|
| `--strip-comments` | AST-aware comment/docstring stripping | 10-30% | NO |
| `--compress-imports` | Deduplicates shared imports across files | 10-20% | NO |
| `--type-prune` | Prunes stdlib/framework/self-documenting callers | 15-40% | NO |
| `--zoom L0..L4` | Progressive disclosure (L0=file list, L4=full) | 50-95% at lower levels | NO |
| `--max-lines` | Hard cap on output lines | variable | NO |
| `--max-bytes` | Hard cap on output bytes | variable | NO |
| `--preset` | Bundles all of the above | 30-70% | NO |
| `--include-body` | Include function bodies in ultracompact | N/A (expands output) | NO |

The MCP `context()` tool only exposes: `depth`, `format`, `budget`, `with_docs`, `session_id`, `delta`.

**Specific code evidence**: In `cli.py:1166-1219`, the context command processes `strip_comments`, `compress_imports`, `type_prune`, `zoom`, `max_lines`, `max_bytes`, and `preset` -- all of which flow through to `get_symbol_context_pack()` and `ContextPackEngine.build_context_pack()`. The MCP tool skips all of these, sending only `format`, `budget`, `with_docs`, `session_id`, `delta` to the daemon (line 239-252).

**Additionally**: The MCP `context()` goes through the daemon socket, which further constrains parameters to whatever the daemon handler accepts. Direct API calls in the MCP server (like `diff_context()` does) would allow passing all parameters.

**Recommendation**: Either:
- (a) Add `strip_comments`, `compress_imports`, `type_prune`, `zoom_level`, `max_lines`, `max_bytes` as MCP tool parameters, OR
- (b) Add a `preset` parameter that maps to the same preset system used by CLI, OR
- (c) Change `context()` to be a direct-call tool (like `diff_context()`) instead of going through the daemon, and expose all parameters

Option (b) is lowest effort and highest leverage. One `preset="compact"` parameter would give Claude Code: `ultracompact + budget=2000 + compress_imports + strip_comments`.

---

## Finding 3: `diff_context()` MCP Tool Lacks Important Parameters

**Location**: `src/tldr_swinton/modules/core/mcp_server.py:562-644`

The MCP `diff_context()` tool is a direct-call tool (good -- bypasses daemon), and it does use the preset system. However, it is missing individual override parameters that the CLI has:

```python
@mcp.tool()
def diff_context(
    project: str = ".",
    preset: str = "compact",      # Good -- uses preset system
    base: str | None = None,
    head: str | None = None,
    budget: int | None = None,     # Good -- can override preset budget
    language: str = "python",
    session_id: str | None = None,
    delta: bool = False,
) -> str:
```

**Missing parameters**:

| Parameter | CLI has it? | MCP has it? | Impact |
|-----------|------------|------------|--------|
| `strip_comments` | Yes (`--strip-comments`) | NO (set by preset only) | Cannot selectively enable/disable |
| `compress_imports` | Yes (`--compress-imports`) | NO (set by preset only) | Cannot selectively enable/disable |
| `type_prune` | Yes (`--type-prune`) | NO (set by preset only) | Cannot selectively enable/disable |
| `compress` | Yes (`--compress blocks/two-stage/chunk-summary`) | NO (set by preset only) | Cannot request block compression without `minimal` preset |
| `zoom` | Yes (`--zoom L0..L4`) | NO | Cannot request signature-only view |
| `max_lines` | Yes (`--max-lines`) | NO | Cannot cap output |
| `max_bytes` | Yes (`--max-bytes`) | NO | Cannot cap output |
| `incremental` | Yes (`--incremental`) | NO | Cannot request unified diffs for partial changes |
| `verify` / `no-verify` | Yes | NO | Cannot control coherence verification |

The `diff_context()` MCP tool resolves preset flags internally (line 601-607):
```python
preset_config = PRESETS.get(preset, PRESETS["compact"])
fmt = preset_config.get("format", "ultracompact")
effective_budget = budget if budget is not None else preset_config.get("budget")
compress = preset_config.get("compress")
strip_comments = preset_config.get("strip_comments", False)
compress_imports = preset_config.get("compress_imports", False)
type_prune = preset_config.get("type_prune", False)
```

This means Claude Code can choose `compact` or `minimal` preset but cannot say "compact preset but with type pruning" or "compact preset but limit to 50 lines."

**Recommendation**: Add `max_lines: int | None = None` and `max_bytes: int | None = None` to the MCP tool. These are the most universally useful caps. For the compression flags, the preset system is reasonable, but consider exposing `zoom_level` as it's orthogonal to presets.

---

## Finding 4: No Claude Code-Optimized Preset

**Location**: `src/tldr_swinton/presets.py:12-33`

Current presets:

```python
PRESETS = {
    "compact": {
        "format": "ultracompact",
        "budget": 2000,
        "compress_imports": True,
        "strip_comments": True,
    },
    "minimal": {
        "format": "ultracompact",
        "budget": 1500,
        "compress": "blocks",
        "compress_imports": True,
        "strip_comments": True,
        "type_prune": True,
    },
    "multi-turn": {
        "format": "cache-friendly",
        "budget": 2000,
        "session_id": "auto",
        "delta": True,
    },
}
```

**Observation**: These presets are reasonable but none of them is specifically tuned for Claude Code's context window and consumption patterns:

1. **`compact`** is the best general-purpose preset but uses budget=2000. Claude Code's 200K context window can handle more when exploring large codebases; 2000 tokens is quite restrictive.

2. **`minimal`** with `blocks` compression is experimental and may lose context needed for editing.

3. **`multi-turn`** uses `cache-friendly` format which is designed for provider-side prompt caching (Anthropic/OpenAI prefix caching). This only helps if the provider is caching prefixes, and the format adds metadata overhead (cache hints, breakpoint markers) that increases tokens.

**Missing**: A preset that combines:
- `ultracompact` format (most token-efficient for single-turn)
- Higher budget (4000-6000) for Claude Code's large context
- `compress_imports` + `strip_comments` + `type_prune` (all proven savings)
- `max_bytes` cap as safety net

**Recommendation**: Add a `claude-code` or `agent` preset:
```python
"agent": {
    "format": "ultracompact",
    "budget": 4000,
    "compress_imports": True,
    "strip_comments": True,
    "type_prune": True,
}
```

This gives maximum compression while allowing enough budget for meaningful context. The `compact` preset's 2000 budget is often too tight for multi-file diff contexts.

---

## Finding 5: `strip_comments` Not Applied in Delta Build Path

**Location**: `src/tldr_swinton/modules/core/contextpack_engine.py:187-329`

The `build_context_pack()` method (non-delta path, line 86-185) applies `strip_comments`:
```python
if strip_comments and code:
    code = strip_code(code, _infer_language_from_symbol_id(candidate.symbol_id))
```

But `build_context_pack_delta()` (line 187-329) does NOT have this logic:
```python
# Lines 224-237 -- no strip_comments parameter at all
code = candidate.code if candidate.code is not None else (info.code if info else None)
# Code goes directly to zooming without stripping
```

The method signature also lacks `strip_comments`:
```python
def build_context_pack_delta(
    self,
    candidates: list[Candidate],
    delta_result: "DeltaResult",
    budget_tokens: int | None = None,
    post_processors: ...,
    zoom_level: ZoomLevel = ZoomLevel.L4,
    compress_imports: bool = False,
    # strip_comments is MISSING
) -> ContextPack:
```

**Impact**: When using delta mode (multi-turn sessions), comments are never stripped even if the preset enables `strip_comments`. The `multi-turn` preset does not enable `strip_comments`, so this is not currently triggered in practice, but it means combining delta + comment stripping is broken.

**Recommendation**: Add `strip_comments: bool = False` parameter to `build_context_pack_delta()` and apply it identically to the non-delta path.

---

## Finding 6: Limited "Already Have" Protocol Beyond Delta Sessions

**Observation**: The only mechanism for Claude Code to say "I already have X, don't resend it" is delta mode via session IDs. This works well for multi-turn conversations where the same session ID is reused.

However, there are scenarios where Claude Code has context from a different source (e.g., it already read a file with `Read`, or it got context from a Serena tool) and doesn't need that file again from tldrs. There is no way to express this.

The `delegate()` tool has a `current_context: list[str]` parameter (line 482) that accepts symbol IDs the agent already has:
```python
def delegate(
    project: str,
    task: str,
    current_context: list[str] | None = None,  # <-- good concept
    ...
```

But `context()` and `diff_context()` do not have an equivalent exclude list.

**Recommendation (low priority)**: Consider adding `exclude: list[str] | None = None` to `diff_context()` to let Claude Code say "skip these symbol IDs." This is lower priority because delta mode handles the main use case (unchanged symbols across turns).

---

## Finding 7: `distill()` and `delegate()` Lack Format Control

**Location**: `src/tldr_swinton/modules/core/mcp_server.py:699-735` and `478-526`

Both `distill()` and `delegate()` produce text output without format negotiation:

```python
@mcp.tool()
def distill(...) -> str:
    ...
    return format_distilled(distilled, budget=budget)  # Always text format
```

The CLI's `distill` command has `--format json` support (cli.py:582), but the MCP tool does not expose this. Similarly, `delegate()` always returns `plan.format_for_agent()` text.

**Impact**: Low -- these tools already produce compact output. But JSON format could be useful for programmatic consumption by Claude Code.

**Recommendation**: Add `format: str = "text"` parameter to `distill()` MCP tool, matching the CLI.

---

## Finding 8: Plugin Commands Have Good Defaults, MCP Schema Does Not

**Location**: `.claude-plugin/commands/context.md` and `.claude-plugin/commands/diff-context.md`

The plugin slash commands encode good defaults in their bash templates:
- `/tldrs-context` uses `--format ultracompact` and `--budget 2000`
- `/tldrs-diff` uses `--budget 2000`

But when Claude Code uses the MCP `tldr-code` tools directly (which it does since the retired skills were replaced by MCP tools), it sees the MCP tool schema defaults:
- `context()`: `format="text"`, `budget=None`
- `diff_context()`: `preset="compact"` (good)

The mismatch means:
- Plugin slash commands produce compact output
- MCP tool calls (the primary interface) produce verbose output unless Claude Code remembers to set parameters

This is especially problematic because the `tldrs-session-start` skill and the MCP tools are the primary interfaces now. The plugin commands are secondary.

**Recommendation**: Align MCP defaults with plugin command defaults. At minimum, `context()` should default to `format="ultracompact"` and `budget=2000`.

---

## Detailed MCP Tool Audit

### Tools with good defaults (no changes needed):

| Tool | Parameters | Assessment |
|------|-----------|------------|
| `diff_context()` | `preset="compact"` | Good -- preset handles compression |
| `distill()` | `budget=1500` | Good -- compact by design |
| `delegate()` | `budget=8000` | Good -- retrieval plan is already compact |
| `structural_search()` | `max_results=50` | Good -- reasonable limit |
| `semantic()` | `k=10` | Good -- reasonable result count |

### Tools with suboptimal defaults:

| Tool | Current Default | Recommended Default | Rationale |
|------|----------------|-------------------|-----------|
| `context()` | `format="text"` | `format="ultracompact"` | 30-50% token savings |
| `context()` | `budget=None` | `budget=4000` | Prevents unbounded output |
| `context()` | No preset support | Add `preset` parameter | Single-knob compression |
| `structure()` | Returns raw dict | No change needed | Already compact |
| `tree()` | Returns full tree | Consider `max_depth` param | Can be very large |

### Tools that are pass-through to daemon (constrained):

| Tool | Goes through daemon? | Can bypass? |
|------|---------------------|-------------|
| `context()` | Yes | Should bypass like `diff_context()` |
| `tree()` | Yes | Fine as-is |
| `structure()` | Yes | Fine as-is |
| `search()` | Yes | Fine as-is |
| `extract()` | Yes | Fine as-is |
| `cfg()` | Yes | Fine as-is |
| `dfg()` | Yes | Fine as-is |
| `slice()` | Yes | Fine as-is |
| `impact()` | Yes | Fine as-is |

The daemon pass-through for `context()` is the main bottleneck because daemon handlers may not accept all the parameters that the direct API accepts.

---

## Tool Granularity Analysis

### Question: Does Claude Code call broad tools when targeted alternatives exist?

**Good granularity (no issues)**:
- `extract()` for single-file structure vs. `structure()` for project-wide
- `slice()` for targeted line analysis vs. `dfg()` for full data flow
- `distill()` for prescriptive summaries vs. `context()` for raw context
- `delegate()` for retrieval planning vs. direct retrieval

**Potential improvement**:
- There is no "get signature only" MCP tool. To get just a function signature, Claude Code must call `context()` with `depth=0`, which still returns more than just the signature. The `zoom` parameter (L1 = signatures only) would solve this but is not exposed in MCP.

- There is no "get callers only" separate from "get full context." `impact()` gives reverse call graph, but `context()` with type_prune could give a more focused caller list. These are not clearly differentiated in the MCP API.

**Recommendation**: Exposing `zoom_level` on `context()` gives the most flexibility -- L0 for file lists, L1 for signatures, L2 for sketches, L4 for full code. This single parameter addresses multiple granularity needs.

---

## Token-Saving Mechanisms: Coverage Matrix

| Mechanism | CLI | MCP `context()` | MCP `diff_context()` | Notes |
|-----------|-----|-----------------|---------------------|-------|
| ultracompact format | `--format ultracompact` | `format` param | Via preset | MCP defaults to text |
| Token budget | `--budget N` | `budget` param | `budget` param | MCP has no default budget |
| Strip comments | `--strip-comments` | NOT EXPOSED | Via preset only | Cannot override preset |
| Compress imports | `--compress-imports` | NOT EXPOSED | Via preset only | Cannot override preset |
| Type pruning | `--type-prune` | NOT EXPOSED | Via preset only | Cannot override preset |
| Zoom levels | `--zoom L0-L4` | NOT EXPOSED | NOT EXPOSED | No progressive disclosure via MCP |
| Block compression | `--compress blocks` | NOT EXPOSED | Via preset only | Only in `minimal` preset |
| Two-stage pruning | `--compress two-stage` | NOT EXPOSED | Via preset only | Legacy, blocks is better |
| Chunk summary | `--compress chunk-summary` | NOT EXPOSED | Via preset only | Not in any preset |
| Delta mode | `--session-id` / `--delta` | `session_id`, `delta` | `session_id`, `delta` | Good coverage |
| Max lines | `--max-lines N` | NOT EXPOSED | NOT EXPOSED | No output cap via MCP |
| Max bytes | `--max-bytes N` | NOT EXPOSED | NOT EXPOSED | No output cap via MCP |
| Presets | `--preset NAME` | NOT EXPOSED | `preset` param | Good for diff_context |
| Machine mode | `--machine` | N/A (always structured) | N/A | MCP returns structured data already |

**Summary**: Of 13 token-saving mechanisms, `context()` MCP exposes 3 (format, budget, delta). `diff_context()` MCP exposes 4 (preset, budget, delta, session_id). The gap is significant.

---

## Recommended Priority Actions

### P0 (Do immediately -- trivial changes, high impact):

1. **Change `context()` MCP default format** from `"text"` to `"ultracompact"`:
   ```python
   # mcp_server.py:208
   format: str = "ultracompact",  # was "text"
   ```

2. **Add default budget to `context()` MCP**:
   ```python
   # mcp_server.py:209
   budget: int | None = 4000,  # was None
   ```

### P1 (Do soon -- medium effort, high impact):

3. **Add `preset` parameter to MCP `context()`** and convert it to a direct-call tool (bypass daemon):
   ```python
   @mcp.tool()
   def context(
       project: str,
       entry: str,
       depth: int = 2,
       language: str = "python",
       format: str = "ultracompact",
       budget: int | None = 4000,
       preset: str | None = None,  # NEW
       with_docs: bool = False,
       strip_comments: bool = True,  # NEW, default True for LLMs
       compress_imports: bool = True,  # NEW, default True for LLMs
       type_prune: bool = False,  # NEW
       zoom_level: str = "L4",  # NEW
       max_lines: int | None = None,  # NEW
       max_bytes: int | None = None,  # NEW
       session_id: str | None = None,
       delta: bool = False,
   ) -> str:
   ```

4. **Add `max_lines` and `max_bytes` to MCP `diff_context()`**:
   ```python
   # mcp_server.py:562
   def diff_context(
       ...
       max_lines: int | None = None,  # NEW
       max_bytes: int | None = None,  # NEW
   ) -> str:
   ```
   Then apply truncation before returning:
   ```python
   output = format_context_pack(result, fmt=fmt)
   if max_lines or max_bytes:
       from .output_formats import truncate_output
       output = truncate_output(output, max_lines=max_lines, max_bytes=max_bytes)
   return output
   ```

5. **Add `strip_comments` to `build_context_pack_delta()`** in `contextpack_engine.py`.

### P2 (Do later -- lower priority):

6. **Add an `agent` preset** tuned for Claude Code.
7. **Add `exclude` parameter** to `diff_context()` for symbol exclusion.
8. **Add `format` parameter** to `distill()` MCP tool.
9. **Consider `max_depth` on `tree()`** for large repos.

---

## Appendix: File References

| File | Absolute Path | Key Lines |
|------|--------------|-----------|
| MCP Server | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/mcp_server.py` | 202-253 (context), 562-644 (diff_context) |
| CLI | `/root/projects/tldr-swinton/src/tldr_swinton/cli.py` | 378-481 (context args), 482-572 (diff-context args) |
| Presets | `/root/projects/tldr-swinton/src/tldr_swinton/presets.py` | 12-33 (preset defs) |
| Output Formats | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/output_formats.py` | 256-325 (format_context_pack), 850-886 (truncate_output) |
| ContextPack Engine | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/contextpack_engine.py` | 86-185 (build_context_pack), 187-329 (build_context_pack_delta) |
| DiffLens Engine | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/engines/difflens.py` | 597-608 (build_diff_context_from_hunks params) |
| Block Compress | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/block_compress.py` | 399-461 (compress_function_body) |
| Strip | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/strip.py` | 232-245 (strip_code) |
| Type Pruner | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/type_pruner.py` | 237-313 (prune_expansion) |
| Import Compress | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/import_compress.py` | 93-110 (compress_imports_section) |
| Zoom | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/zoom.py` | 12-17 (ZoomLevel enum), 243-262 (format_at_zoom) |
| Plugin context.md | `/root/projects/tldr-swinton/.claude-plugin/commands/context.md` | 22 (bash template with --format ultracompact) |
| Plugin diff-context.md | `/root/projects/tldr-swinton/.claude-plugin/commands/diff-context.md` | 19 (bash template) |
| Delta Engine | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/engines/delta.py` | 57-59 (delta processors) |
| Distill Formatter | `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/distill_formatter.py` | 92-168 (format_distilled) |
