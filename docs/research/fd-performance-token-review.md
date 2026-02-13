# fd-performance: Token Efficiency Review for Claude Code Consumers

**Reviewer**: fd-performance (flux-drive)
**Date**: 2026-02-12
**Scope**: Output bloat, budget enforcement gaps, redundant data, format efficiency, MCP overhead, lazy loading gaps
**Codebase version**: commit 71e1d22 (main)

---

## Executive Summary

tldr-swinton already has an impressive array of token-saving mechanisms (15+), but there are **6 concrete opportunities** to reduce token output by an estimated **8-20% in common MCP workflows**. The highest-impact findings are: (1) meta dict bloat in diff-context output (~50-150 tokens/slice wasted on zero-value fields), (2) full-length SHA-256 ETags consuming ~16 tokens each when 8-12 chars suffice, and (3) MCP daemon wrapper overhead bleeding through to every dict-returning tool.

---

## Finding 1: Meta Dict Bloat in Diff-Context Output (HIGH IMPACT)

**File**: `src/tldr_swinton/modules/core/engines/difflens.py`, lines 760-765
**File**: `src/tldr_swinton/modules/core/engines/difflens.py`, lines 827-828

### Problem

When building diff-context candidates, every symbol gets a meta dict with four fields:

```python
meta: dict[str, object] = {
    "diff_lines": _to_ranges(sorted(symbol_diff_lines.get(symbol_id, []))),
    "block_count": block_count,
    "dropped_blocks": dropped_blocks,
    "summary": summary,
}
```

At line 828, this meta dict is **unpacked directly into the output slice**:

```python
if item.meta:
    entry.update(item.meta)
```

This means every slice in the final output contains:
- `"block_count": 0` -- present on every non-compressed symbol (the majority)
- `"dropped_blocks": 0` -- same, always 0 when compression is not used
- `"summary": null` -- always null unless `compress == "chunk-summary"`, which is rare
- `"diff_lines": []` -- empty list for callers/callees (they have no diff lines)

For a typical diff-context with 15-25 symbols, about 60-80% are callers/callees with all-zero/null meta. Each such symbol contributes roughly **6-10 tokens** of zero-value meta (`"block_count":0,"dropped_blocks":0,"summary":null,"diff_lines":[]`).

### Estimated Savings

For a 20-symbol diff context: 12-16 callers/callees x ~8 tokens = **96-128 tokens** per request. Under a 2000-token budget, that is **5-6%** of the budget wasted on fields that convey no information.

### Recommended Fix

Only include meta fields that have non-default values:

```python
meta: dict[str, object] = {}
diff_ranges = _to_ranges(sorted(symbol_diff_lines.get(symbol_id, [])))
if diff_ranges:
    meta["diff_lines"] = diff_ranges
if block_count > 0:
    meta["block_count"] = block_count
if dropped_blocks > 0:
    meta["dropped_blocks"] = dropped_blocks
if summary:
    meta["summary"] = summary
```

This change is purely output-facing; no internal logic depends on these being present.

---

## Finding 2: Full SHA-256 ETags Are 2x Longer Than Needed (MEDIUM IMPACT)

**File**: `src/tldr_swinton/modules/core/contextpack_engine.py`, line 572

### Problem

```python
def _compute_etag(signature: str, code: str | None) -> str:
    payload = signature
    if code:
        payload = f"{signature}\n{code}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

Every ETag is a full 64-character SHA-256 hex digest. ETags are used for two purposes:
1. **Delta detection** in `state_store.py` -- comparing current vs cached ETags
2. **Output inclusion** in every ContextSlice, serialized in every format

For delta detection, collision resistance beyond 16 hex chars (64 bits) is unnecessary given the cardinality of symbols in a single project (typically <100k). For output, each 64-char ETag costs approximately **16 tokens** (at ~4 chars/token for hex strings).

With 20 slices in a diff-context pack, ETags contribute **~320 tokens** to the output. Truncating to 16 chars would save **~160 tokens per request** while maintaining negligible collision probability.

### Estimated Savings

~160 tokens per diff-context request (20 slices), or **~8% of a 2000-token budget**.

### Recommended Fix

```python
return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
```

Note: The `state_store` would need to be migrated (or handle both lengths during transition). A simpler option: truncate only in the `_contextpack_to_dict` serialization path, keeping full ETags internally.

---

## Finding 3: MCP Daemon Wrapper Overhead on Dict-Returning Tools (MEDIUM IMPACT)

**File**: `src/tldr_swinton/modules/core/mcp_server.py`, lines 116-119, 145-196
**File**: `src/tldr_swinton/modules/core/daemon.py`, all handler responses

### Problem

Every MCP tool that returns `dict` (tree, structure, search, extract, cfg, dfg, slice, impact, dead, arch, calls, imports, importers, diagnostics, change_impact, status) passes the raw daemon response through. The daemon wraps every response with:

```python
{"status": "ok", ...actual_data...}
```

On error:
```python
{"status": "error", "message": "..."}
```

The `"status": "ok"` field is **never consumed by Claude Code** -- MCP tools succeed or throw. When the tool succeeds, the `"status": "ok"` key-value pair is pure waste, adding **~3 tokens per response**. More importantly, the `result` wrapper in some handlers adds nesting:

```python
return {"status": "ok", "result": result}  # daemon.py
```

Then in mcp_server.py:
```python
return _send_command(project, {"cmd": "extract", "file": file})  # Returns full wrapper
```

The consumer sees `{"status":"ok","result":{...}}` when they only need `{...}`.

### Estimated Savings

For single-response tools: ~3-5 tokens overhead. For tools returning large dicts (structure, calls, tree): the overhead is proportionally minor but still unnecessary. Across a session with 10-20 tool calls: **30-100 tokens wasted**.

### Recommended Fix

Strip the wrapper in `_send_command` or create a `_send_and_unwrap`:

```python
def _send_and_unwrap(project: str, command: dict) -> dict:
    result = _send_command(project, command)
    if result.get("status") == "ok":
        return result.get("result", result)
    raise RuntimeError(result.get("message", "Unknown error"))
```

Note: The `context` tool already handles this via `_format_context_result`. The dict-returning tools do not.

---

## Finding 4: Ultracompact Format Emits Trailing Whitespace and Empty Lines (LOW-MEDIUM IMPACT)

**File**: `src/tldr_swinton/modules/core/output_formats.py`, lines 444-460, 765-810

### Problem

The ultracompact format emits an **empty line after every symbol** (line 458: `lines.append("")`), and the cache-friendly format does the same (line 674: `dynamic_parts.append("")`). For 20 symbols, this adds 20 blank lines = 20 newline characters. While newlines are cheap (typically sub-1 token each in modern tokenizers), the pattern compounds:

```
P0:foo def foo(x) @12
  calls: P0:bar, P0:baz

P0:bar def bar(y) @24

P0:baz def baz(z) @36

```

Every `""` line becomes `\n\n` in the output (a blank line). Combined with the `.rstrip()` on line 787:

```python
lines.append(f"{display} {signature} {line_info} [{relevance}]{unchanged_marker}".rstrip())
```

The `.rstrip()` removes trailing spaces but the line itself may still contain trailing space between `{line_info}` and `[{relevance}]` when `line_info` is empty (no line range). This generates patterns like `P0:foo def foo(x)  [callee]` (double space before the relevance tag).

### Estimated Savings

For 20 symbols: ~10-15 tokens from blank-line elimination + ~5 tokens from double-space cleanup = **~15-20 tokens per request**.

### Recommended Fix

1. Use single newlines between symbols (no blank line separators in ultracompact -- the format name implies maximum density)
2. Filter empty `line_info` before concatenation:

```python
parts = [display, signature]
if line_info:
    parts.append(line_info)
parts.append(f"[{relevance}]")
if unchanged_marker:
    parts.append(unchanged_marker)
lines.append(" ".join(parts))
```

---

## Finding 5: Budget Enforcement Gaps in Multiple Code Paths (MEDIUM IMPACT)

### 5a. `diff_context` MCP tool does not pass budget to `include_symbol_bodies`

**File**: `src/tldr_swinton/modules/core/mcp_server.py`, lines 596-644

The `diff_context` MCP tool calls `_get_diff_context()` with `budget_tokens=effective_budget`. However, the DiffLens engine internally calls `ContextPackEngine.build_context_pack()` which enforces the budget. BUT: when `compress` is None (the default for `compact` preset), the code at `difflens.py:722-730` extracts windowed code using `_extract_windowed_code`, which has no direct budget constraint on the size of the extracted window -- it only uses adaptive context lines (2-8). If a symbol has many scattered diff lines, the merged windows can produce very large code snippets that the ContextPackEngine then must handle via budget enforcement.

The issue: the budget check in `ContextPackEngine.build_context_pack()` (lines 147-176) works at the **per-slice granularity**. If a single slice's code is 1500 tokens and the budget is 2000, it gets included. But if the next slice is 600 tokens, it gets dropped entirely. There is no **within-slice truncation** -- slices are all-or-nothing with a signature-only fallback.

This means one large slice can consume the entire budget, leaving no room for context from callers/callees.

### 5b. `distill_formatter` uses its own `_estimate_tokens` (chars//4) instead of shared `token_utils.estimate_tokens`

**File**: `src/tldr_swinton/modules/core/distill_formatter.py`, line 21-22

```python
def _estimate_tokens(text: str) -> int:
    return max(0, len(text) // 4)
```

The shared `token_utils.estimate_tokens` tries to use `tiktoken` first (accurate) and only falls back to `len//4`. The distill formatter always uses the inaccurate fallback, which can **underestimate** by 20-30% for code with many special characters, leading to budget overruns.

### 5c. `_two_stage_prune` reserves `max_tokens = sum(sizes)` when budget is None

**File**: `src/tldr_swinton/modules/core/engines/difflens.py`, lines 492-495

```python
if budget_tokens is not None:
    max_tokens = budget_tokens
else:
    max_tokens = sum(sizes)  # no budget = keep everything eligible
```

When called without a budget (which happens when the outer caller handles budget enforcement), this is correct. But the knapsack DP (line 512) caps `W = min(remaining_budget, 10000)` regardless, meaning the DP table is bounded. However, the `sizes` computation at line 445 uses `len(block_text) // 4` which is a rough token estimate. If the actual code is 2x more tokens due to special characters, the "kept everything" decision is made on underestimated sizes.

### Estimated Savings

5a: Not a token savings directly, but prevents budget blowouts where one large slice monopolizes the budget. Could save **200-500 tokens** in pathological cases (large refactors touching one huge function).

5b: Fixing the estimator in distill_formatter could prevent **50-200 tokens of budget overrun**.

### Recommended Fix

5a: Add within-slice windowing for slices that exceed 50% of the remaining budget. If a code slice is >50% of budget, truncate to the most relevant windows (diff overlap lines + 3 lines context).

5b: Replace the local `_estimate_tokens` with `from .token_utils import estimate_tokens`.

---

## Finding 6: Redundant Work When `context` and `diff_context` Are Called in Sequence (MEDIUM IMPACT)

### Problem

When Claude Code's autonomous skill `tldrs-session-start` runs, it calls `diff_context`. Then if the agent later calls `context` for a specific symbol, there is **complete overlap** in the callers/callees expansion. Both tools build a `ProjectIndex` from scratch (unless the daemon caches it in `SalsaDB`).

More importantly, the **output** from both tools is sent to the LLM. If `diff_context` already returned signatures for `foo`, `bar`, and `baz`, and then `context foo` returns the same signatures plus code for `foo`, the LLM sees the signatures twice.

### Estimated Savings

In a typical session: `diff_context` returns ~20 symbols (~2000 tokens). A subsequent `context` call returns ~10 symbols (~500 tokens, signatures-only). Overlap is typically 5-8 symbols = **~80-150 tokens duplicated**.

### Recommended Fix

This is a consumer-side problem, not a tldrs problem per se. However, tldrs could help by:
1. Including a `session_fingerprint` in the `diff_context` output that `context` could use to skip already-delivered symbols.
2. Recommending in the skill/command docs that `context` be used with `--delta` after `diff_context` in the same session, which already deduplicates via the state store.

The existing delta mode already solves this for multi-turn scenarios. The gap is that `diff_context` (via MCP tool) and `context` (via MCP tool) don't share session state unless the consumer explicitly provides the same `session_id`.

---

## Finding 7: `elide_nulls` in Packed-JSON Does Not Elide Zero-Value Numerics (LOW IMPACT)

**File**: `src/tldr_swinton/modules/core/json_codec.py`, lines 103-104

```python
def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
```

This elides `None`, empty strings, empty lists, and empty dicts, but NOT `0` or `False`. In packed-json output, fields like `"block_count": 0` and `"dropped_blocks": 0` survive elision. Since these zero values carry no information (zero blocks processed = no compression happened), they should be elided.

### Estimated Savings

~2-4 tokens per slice with zero-value meta = **~30-60 tokens per 20-slice pack** in packed-json format.

### Recommended Fix

Either:
1. Add `value == 0` and `value is False` to `_is_empty` (with care -- `budget_used: 0` is meaningful).
2. Better: fix at the source (Finding 1) so zeros are never emitted.

---

## Finding 8: Cache-Friendly Format Stats Footer Is Redundant with Cache Hints (LOW IMPACT)

**File**: `src/tldr_swinton/modules/core/output_formats.py`, lines 693-703

The cache-friendly format emits both:
1. A machine-readable `cache_hints` JSON blob (line 711-718)
2. A human-readable `STATS` footer (line 694-695): `## STATS: Prefix ~X tokens | Dynamic ~Y tokens | Total ~Z tokens`
3. A human-readable `Cache` line (line 703): `## Cache: N unchanged, M changed (P% hit rate)`

The STATS footer duplicates information already in `cache_hints` and the Cache line duplicates `cache_stats` from the pack. Together they consume **~30-40 tokens** per response.

### Estimated Savings

~30-40 tokens per cache-friendly response.

### Recommended Fix

Remove the STATS footer and Cache line, keeping only the machine-readable `cache_hints` JSON. LLMs can parse JSON; they don't need a human-readable duplicate.

---

## Finding 9: Lazy Loading Gap -- `_imports_for_symbol` Extracts Full File for Every Symbol (LOW-MEDIUM IMPACT)

**File**: `src/tldr_swinton/modules/core/engines/difflens.py`, lines 667-682

```python
def _imports_for_symbol(symbol_id: str) -> list[str]:
    if ":" not in symbol_id:
        return []
    rel_path = symbol_id.split(":", 1)[0]
    if rel_path in file_imports:
        return file_imports[rel_path]
    file_path = project / rel_path
    if not file_path.is_file():
        file_imports[rel_path] = []
        return []
    try:
        info = import_extractor.extract(str(file_path))  # FULL FILE EXTRACTION
        file_imports[rel_path] = [imp.statement() for imp in info.imports]
    except Exception:
        file_imports[rel_path] = []
    return file_imports[rel_path]
```

This calls `HybridExtractor.extract()` on the **full file** just to get imports. The HybridExtractor does full AST parsing (functions, classes, methods, decorators, etc.) when only imports are needed. This is not a token-output issue but a **latency/CPU waste** issue that indirectly affects the user experience.

Note: the `file_imports` dict provides per-file caching, so this is only done once per file. But for a diff touching 5 files with 10 symbols across them, that is still 5 full AST parses instead of 5 import-only parses.

### Recommended Fix

Use a lighter-weight import extractor. The `get_imports` API function in `api.py` may already do this; investigate whether it can be used instead.

---

## Finding 10: `format_at_zoom` Always Calls `extract_body_sketch` at L2 Even When Code Is None (LOW IMPACT)

**File**: `src/tldr_swinton/modules/core/zoom.py`, lines 256-257

```python
if zoom is ZoomLevel.L2:
    sketch = extract_body_sketch(code or "", language)
```

When `code` is `None` (signature-only fallback due to budget), this calls `extract_body_sketch("")` which creates a tree-sitter parser, parses an empty string, walks the empty tree, and returns `""`. This happens for every signature-only slice at zoom L2.

### Estimated Savings

Zero token savings (no output change), but prevents ~5ms of wasted tree-sitter work per signature-only slice. In a 20-slice pack with 15 signature-only slices, that is ~75ms of wasted CPU.

### Recommended Fix

```python
if zoom is ZoomLevel.L2:
    sketch = extract_body_sketch(code, language) if code else ""
```

---

## Summary Table

| # | Finding | Impact | Est. Savings (tokens) | Difficulty |
|---|---------|--------|----------------------|------------|
| 1 | Meta dict zero-value bloat | HIGH | 96-128 per request | Easy |
| 2 | Full SHA-256 ETags (64 chars) | MEDIUM | ~160 per request | Easy (output-side) |
| 3 | MCP daemon `status:ok` wrapper | MEDIUM | 30-100 per session | Easy |
| 4 | Ultracompact blank lines + double spaces | LOW-MED | 15-20 per request | Easy |
| 5 | Budget enforcement gaps | MEDIUM | 200-500 (pathological) | Medium |
| 6 | Redundant data across context+diff_context | MEDIUM | 80-150 per session | Medium (consumer-side) |
| 7 | `elide_nulls` doesn't elide zeros | LOW | 30-60 per packed-json | Easy |
| 8 | Cache-friendly duplicate stats | LOW | 30-40 per request | Easy |
| 9 | Full AST parse for import-only extraction | LOW-MED | 0 tokens (latency) | Medium |
| 10 | `extract_body_sketch("")` wasted work | LOW | 0 tokens (CPU) | Easy |

**Combined impact of Findings 1+2+4 (easy, output-only fixes)**: ~270-310 tokens per diff-context request, or **~14-15% of a 2000-token budget**.

---

## Appendix: What Already Works Well

The following mechanisms are well-implemented and should NOT be modified:

1. **Path reference compression** (`P0=file.py P1=other.py`) -- efficient, well-tested
2. **Signature-only fallback** when budget exceeded -- clean graceful degradation
3. **Import compression** (common header + per-file unique) -- well-architected
4. **Delta mode with ETags** -- correct architecture, just needs shorter ETags in output
5. **Two-stage knapsack pruning** -- algorithmically sound for block selection
6. **JSON key aliases** (`id->i`, `signature->g`, etc.) -- good in packed-json
7. **Adaptive context windows** (2-8 lines based on density) -- smart heuristic
8. **Zoom levels** (L0-L4) -- clean progressive disclosure API
9. **Budget-aware calls limiting** (`compute_max_calls`) -- nice touch
10. **Type-directed pruning** -- reduces irrelevant caller/callee expansion

The codebase demonstrates strong token-awareness overall. The findings above represent incremental improvements on an already well-optimized system.
