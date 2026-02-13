# qg-fd-api-surface: API Surface & Backward Compatibility Review

**Reviewer**: qg-fd-api-surface (Quality & Style Reviewer, API surface specialist)
**Date**: 2026-02-12
**Scope**: Backward compatibility, parameter naming, default value choices, docstring accuracy, public API consistency
**Context**: This diff changes MCP API defaults and adds a `compact` mode to `extract()`. MCP is consumed by Claude Code and other LLM agents.

---

## Executive Summary

**Severity: MODERATE.** The diff contains **3 breaking changes**, **2 misleading docstrings**, and **1 inconsistent schema key**. All findings are fixable, but the `context()` default change is backward-incompatible for existing MCP consumers that relied on `format="text"`.

**Key Findings:**

1. **Breaking change**: `context()` MCP default changed from `format="text"` to `format="ultracompact"` — existing callers that expected human-readable text will get compressed output
2. **Breaking change**: `context()` default budget changed from `None` (unlimited) to `4000` — output is now capped by default
3. **Misleading docstring**: `extract()` says "Returns imports, functions, classes, and intra-file call graph" but `compact=True` omits imports and call_graph
4. **Schema inconsistency**: `compact_extract()` uses `"line"` but full `extract()` uses `"line_number"`
5. **Missing validation**: `compact` flag not checked for compatibility with `--class`/`--function`/`--method` filters in CLI
6. **Documentation gap**: `compact=True` bypasses daemon but docstring doesn't mention this (latency/caching implications)

**Recommendation**: Accept the changes but fix the docstrings and add CLI validation. The default changes are justified for LLM consumers (MCP is explicitly for AI tools), but consider a deprecation notice.

---

## Finding 1: `context()` Default Change Is Backward-Incompatible

**Location**: `src/tldr_swinton/modules/core/mcp_server.py:213-214`

**The Change:**
```python
# Before:
format: str = "text",
budget: int | None = None,

# After:
format: str = "ultracompact",
budget: int | None = 4000,
```

**Impact Analysis:**

| Scenario | Before | After | Breaks? |
|----------|--------|-------|---------|
| MCP caller with no params | Human-readable text, unlimited | Compressed, capped at 4000 | YES |
| MCP caller specifying `format="text"` | Human-readable, unlimited | Human-readable, capped at 4000 | PARTIAL (budget cap) |
| MCP caller specifying both params | Explicit override | Explicit override | NO |

**Who is affected?**

- Any MCP client that calls `context()` without specifying `format` — they will see compressed output instead of human-readable text
- Any MCP client that relies on unlimited output (e.g., for exhaustive call graph exploration) — they will now be capped at 4000 tokens

**Justification from the MCP server description (line 4)**:
```python
"""
Provides 1:1 mapping with TLDR daemon commands, enabling AI tools
(OpenCode, Claude Desktop, Claude Code) to use TLDR's code analysis.
"""
```

The server is explicitly **for AI tools**, not humans. The `ultracompact` format is purpose-built for LLM consumption (path IDs, no emoji, whitespace-stripped). The `text` format is designed for human terminal output.

**But**: The original default was `text`, which suggests either:
1. An initial design choice to be human-friendly first, OR
2. A mistake (should have been `ultracompact` from the start)

**Backward Compatibility Mitigation:**

Option A: **Add a migration warning** in the changelog and MCP server docstring:
```python
"""
TLDR MCP Server - Model Context Protocol interface for TLDR.

⚠️  Breaking change in v0.X.0: `context()` now defaults to format="ultracompact"
and budget=4000. To get the old behavior, explicitly pass format="text" and budget=None.
"""
```

Option B: **Add a temporary `legacy` preset** that preserves old defaults:
```python
# In mcp_server.py
if preset == "legacy":
    format = "text"
    budget = None
```

Option C: **Accept the break** — justified because the server is for LLMs, not humans. Document in changelog and bump minor version.

**Recommendation**: **Option C with changelog notice**. The MCP server is explicitly for AI tools, and the plugin commands already use `ultracompact` (they know better). The old defaults were suboptimal.

---

## Finding 2: `extract()` Docstring Is Misleading for `compact=True`

**Location**: `src/tldr_swinton/modules/core/mcp_server.py:187-201`

**Current Docstring:**
```python
@mcp.tool()
def extract(file: str, compact: bool = False) -> dict:
    """Extract full code structure from a file.

    Returns imports, functions, classes, and intra-file call graph.

    Args:
        file: Path to source file
        compact: If True, return signatures and line numbers only (~87% smaller).
                 Use for LLM context injection; omits call_graph, params, is_async.
    """
```

**The Problem**: The top-level docstring says "Returns imports, functions, classes, and intra-file call graph" but this is only true when `compact=False`. When `compact=True`, the function returns **no imports** and **no call_graph**.

**Evidence from `compact_extract()` (api.py:755)**:
```python
# Omit imports (available from the file itself) and call_graph (rarely needed)
return result
```

The comment explicitly says imports and call_graph are omitted.

**Fix**: Make the docstring conditional or more accurate:

```python
def extract(file: str, compact: bool = False) -> dict:
    """Extract code structure from a file.

    Args:
        file: Path to source file
        compact: If True, return signatures and line numbers only (~87% smaller).
                 Omits call_graph, imports, params, is_async, and empty decorators/docstrings.
                 Use for LLM context injection where full detail is not needed.

    Returns:
        When compact=False: Full structure with imports, functions, classes, call_graph.
        When compact=True: Minimal structure with function/class names, signatures, line numbers.
    """
```

This accurately describes what both modes return.

---

## Finding 3: Schema Key Inconsistency — `line` vs `line_number`

**Location**: `src/tldr_swinton/modules/core/api.py:725, 739`

**The Issue**: `compact_extract()` uses `"line"` as the dict key:
```python
entry: dict = {"name": f["name"], "signature": f["signature"], "line": f["line_number"]}
#                                                                ^^^^
```

But the full `extract_file()` uses `"line_number"` (from `FunctionInfo.to_dict()`).

**Why This Matters:**

1. **Callers that rely on key names will break** if they parse compact output expecting `line_number`
2. **Schema documentation/typing will be inconsistent** if the compact and full modes have different keys
3. **No migration path** — a caller cannot write code that works with both modes

**Example Broken Code:**
```python
result = extract(file, compact=True)
for fn in result["functions"]:
    print(f"{fn['name']} at line {fn['line_number']}")  # KeyError: 'line_number'
```

**Options:**

Option A: **Change compact to use `line_number`** for consistency:
```python
entry: dict = {"name": f["name"], "signature": f["signature"], "line_number": f["line_number"]}
```

Option B: **Change full extract to use `line`** (breaking for existing consumers of full extract)

Option C: **Document the difference** and require callers to handle both:
```python
line_no = fn.get("line") or fn.get("line_number")
```

**Recommendation**: **Option A**. The compact format is new; changing it now is safe. The full extract schema is established and should not change.

---

## Finding 4: `compact` Flag Not Validated Against CLI Filters

**Location**: `src/tldr_swinton/cli.py:1071-1119`

**Current Code:**
```python
if getattr(args, "compact", False):
    from .modules.core.api import compact_extract
    result = compact_extract(args.file)
else:
    result = extract_file(args.file)

# Apply filters if specified
filter_class = getattr(args, "filter_class", None)
filter_function = getattr(args, "filter_function", None)
filter_method = getattr(args, "filter_method", None)

if filter_class or filter_function or filter_method:
    # ... filtering code runs on compact result
```

**The Problem**: The `--compact` flag bypasses `extract_file()` and returns a minimal schema, then the filtering code (lines 1082-1118) runs on this minimal output. The filters expect keys like `"line_number"`, `"params"`, `"decorators"`, etc., which may or may not exist in compact output.

**Example User Command:**
```bash
tldr extract myfile.py --compact --function my_function
```

This will:
1. Call `compact_extract(myfile.py)` → returns `{"functions": [{"name": "my_function", "signature": "...", "line": 42}]}`
2. Try to filter `result["functions"]` where `f.get("name") == "my_function"`

This **happens to work** because `compact_extract` still includes `"name"` in function dicts. But it's **semantically weird** — why apply a filter to compact output that already drops most fields?

**Better Behavior:**

Option A: **Disallow `--compact` with filters**:
```python
if getattr(args, "compact", False) and (filter_class or filter_function or filter_method):
    print("Error: --compact cannot be used with --class/--function/--method filters", file=sys.stderr)
    sys.exit(1)
```

Option B: **Apply filters before compacting**:
```python
result = extract_file(args.file)
# Apply filters
if filter_class or filter_function or filter_method:
    # ... filtering logic
# Then compact if requested
if getattr(args, "compact", False):
    result = _compact_result(result)  # helper to convert full → compact
```

**Recommendation**: **Option A** — simpler and clearer. If you want a filtered view, use full extract. Compact is for bulk structure only.

---

## Finding 5: `compact_extract()` Bypasses Daemon (Undocumented Latency Implication)

**Location**: `src/tldr_swinton/modules/core/mcp_server.py:197-201`

**Current Code:**
```python
if compact:
    from .api import compact_extract
    return compact_extract(file)
project = str(Path(file).parent)
return _send_command(project, {"cmd": "extract", "file": file})
```

**The Observation**: When `compact=True`, the MCP tool bypasses the daemon and calls `compact_extract()` directly. When `compact=False`, it goes through the daemon socket (`_send_command()`).

**Why This Matters:**

1. **Latency**: Direct calls have no socket overhead or daemon startup delay
2. **Caching**: The daemon may cache parsed AST results; direct calls do not benefit from this
3. **Concurrency**: Daemon can handle concurrent requests; direct calls block the MCP server process

**Implication for MCP Callers:**

- `extract(file, compact=True)` — fast, no startup delay, but no cache
- `extract(file, compact=False)` — potentially slower first call (daemon startup), but benefits from daemon-side caching on repeated calls

**The docstring does not mention this tradeoff.**

**Recommendation**: Add a note to the docstring:
```python
compact: If True, return signatures and line numbers only (~87% smaller).
         Bypasses daemon for lower latency; use for one-off structure queries.
         Omits call_graph, imports, params, is_async, and empty decorators/docstrings.
```

---

## Finding 6: `4000` Budget Default — Is This a Good Choice?

**Location**: `src/tldr_swinton/modules/core/mcp_server.py:214`

**The Change**:
```python
budget: int | None = 4000,
```

**Context from Other Files**:

- CLI `context` subcommand: no default budget (`--budget` is optional, defaults to `None`)
- Plugin `/tldrs-context` command: uses `--budget 2000`
- `compact` preset: `budget=2000`
- `agent` preset (recommended in fd-api-surface-token-review.md): `budget=4000`

**The Question**: Is `4000` too restrictive for large codebases? Too permissive for focused queries?

**Analysis**:

| Budget | Use Case | Risk |
|--------|----------|------|
| None (unlimited) | Large codebase exploration, exhaustive call graphs | Output explosion, 100K+ tokens |
| 1500 (minimal preset) | Targeted editing, diff review | Too restrictive for deep call stacks |
| 2000 (compact preset) | General-purpose single-file context | Slightly tight for multi-file |
| 4000 (new default) | Multi-file context, moderate depth=2-3 | Reasonable middle ground |
| 8000 (delegate default) | Retrieval planning, architectural queries | May be excessive for simple queries |

**Comparison with Claude Code Context Window**:

Claude Code (Opus 4.6) has a 200K token context window. A 4000-token context is **2% of the window** — very conservative. The restriction is not about filling Claude's context; it's about **not wasting tokens on irrelevant code**.

**Recommendation**: **4000 is reasonable** for a default. It prevents unbounded output while allowing meaningful multi-file context. Callers that need more can pass `budget=None` or `budget=10000`.

**But**: Document this clearly in the changelog and MCP docstring as a breaking change from `None` → `4000`.

---

## Questions from the Review Prompt — Answered

### 1. Is the `context()` default change backward-compatible?

**No.** Existing MCP callers that relied on `format="text"` (human-readable) or `budget=None` (unlimited) will break. However, this is **justified** because:

- MCP server is explicitly for AI tools (docstring line 4)
- The plugin commands already use `ultracompact` (they know better)
- Old defaults were suboptimal for LLM consumption

**Mitigation**: Add a changelog notice and bump minor version per semver (breaking change in a 0.x release is allowed).

---

### 2. Is the `extract()` docstring now misleading?

**Yes.** The docstring says "Returns imports, functions, classes, and intra-file call graph" but `compact=True` returns **none of the imports** and **none of the call_graph**.

**Fix**: Rewrite docstring to clarify:
```python
"""Extract code structure from a file.

Returns:
    When compact=False: Full structure with imports, functions, classes, call_graph.
    When compact=True: Minimal structure with function/class names, signatures, line numbers only.
                       Omits imports, call_graph, params, is_async.
"""
```

---

### 3. Does the `compact_extract` output schema key naming match the full extract?

**No.** Compact uses `"line"`, full uses `"line_number"`.

**Fix**: Change compact to use `"line_number"` for consistency:
```python
entry: dict = {"name": f["name"], "signature": f["signature"], "line_number": f["line_number"]}
```

---

### 4. Is the `--compact` flag compatible with the existing `--class`/`--function`/`--method` filter flags?

**Technically yes, but semantically questionable.** The filtering code runs on compact output, which happens to work because compact still includes the `"name"` field. But it's weird to filter a minimal view.

**Fix**: Disallow the combination:
```python
if getattr(args, "compact", False) and (filter_class or filter_function or filter_method):
    print("Error: --compact cannot be used with --class/--function/--method filters", file=sys.stderr)
    sys.exit(1)
```

---

### 5. Is `4000` a good default budget?

**Yes**, for the following reasons:

1. **Claude Code context window is 200K** — 4000 is only 2%, very conservative
2. **Prevents unbounded output** that wastes tokens on irrelevant code
3. **Matches the recommended `agent` preset** from the token review (fd-api-surface-token-review.md)
4. **Higher than `compact` preset (2000)** but lower than `delegate` (8000) — reasonable middle ground

Callers needing more can pass `budget=None` (unlimited) or a higher number.

---

## Recommended Fixes (Priority Order)

### P0 (Must fix before merge):

1. **Fix `extract()` docstring** to accurately describe what `compact=True` returns
2. **Change compact schema** to use `"line_number"` instead of `"line"`
3. **Add CLI validation** to disallow `--compact` with `--class/--function/--method`

### P1 (Should fix before release):

4. **Add changelog notice** for `context()` breaking change (format and budget defaults)
5. **Update MCP server docstring** to warn about the breaking change
6. **Document latency tradeoff** in `extract()` docstring (daemon bypass for compact mode)

### P2 (Nice to have):

7. **Add a `legacy` preset** for backward compatibility (or document the manual override)
8. **Consider renaming `compact`** → `minimal` to match the preset naming (minor)

---

## Appendix: Diff Impact Matrix

| Change | File | Backward Compatible? | Justification | Fix Required? |
|--------|------|---------------------|--------------|---------------|
| `context()` format default | mcp_server.py:213 | NO | MCP is for LLMs, not humans | Changelog + docstring |
| `context()` budget default | mcp_server.py:214 | NO | Prevents unbounded output | Changelog + docstring |
| `extract()` compact param | mcp_server.py:187 | YES (new param) | Optional, defaults to False | Fix docstring |
| `compact_extract()` function | api.py:714-756 | YES (new function) | Not breaking existing APIs | Fix schema keys |
| CLI `--compact` flag | cli.py:376-380 | YES (new flag) | Optional flag | Add validation |

---

## Conclusion

**Overall Assessment**: The changes improve token efficiency for LLM consumers (good), but introduce **2 breaking changes** and **3 correctness issues**. All issues are fixable with docstring updates, schema alignment, and validation.

**Ship or Block?**

- **Ship** the `extract(compact=True)` addition after fixing schema keys and docstring
- **Ship** the `context()` default changes after adding changelog notice and migration docs
- **Block** if the schema inconsistency (`line` vs `line_number`) is not fixed — this will break callers

**Recommended Next Steps**:

1. Fix schema: `"line"` → `"line_number"` in compact_extract
2. Fix docstrings: clarify what compact mode returns
3. Add validation: disallow `--compact` with filters in CLI
4. Add changelog: document the `context()` breaking change
5. Update MCP docstring: warn about format/budget default change
