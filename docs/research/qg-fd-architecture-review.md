# Architecture Review: Phase 1 Token Efficiency Changes

**Reviewed:** 2026-02-12
**Scope:** Compact extract feature + hook/skill refactoring
**Focus:** Module boundaries, coupling, patterns, complexity

---

## 1. Boundaries & Coupling

### ✅ CLEAN: API Layer Structure
**api.py module boundary is well-defined:**
- `compact_extract()` correctly lives alongside `extract_file()` as a thin adapter
- Delegates to `extract_file()` then transforms — single responsibility maintained
- Both functions accept same parameters (`file_path`, `base_path`) — consistent interface
- No leakage of internal representation details

**Coupling assessment:**
- `compact_extract()` depends on `extract_file()`'s dict schema (acceptable sibling coupling)
- Brittle keys: `"functions"`, `"classes"`, `"methods"`, `"decorators"`, `"docstring"`, `"signature"`, `"line_number"`, `"bases"`
- **Risk:** If `extract_file()` output schema changes, `compact_extract()` breaks silently
- **Mitigation present:** Both live in same module, changed together
- **Missing:** No shared schema definition or validation layer

### ✅ CLEAN: CLI Integration
**cli.py uses lazy import correctly:**
```python
if getattr(args, "compact", False):
    from .modules.core.api import compact_extract
    result = compact_extract(args.file)
```
- Import happens only when feature is used
- No performance penalty for default path
- Clear intent: `compact_extract` is opt-in behavior

**Pattern consistency:**
- `extract_file()` imported at module top (always needed)
- `compact_extract()` imported conditionally (optional feature)
- Follows "import at use site for optional features" convention

### ⚠️ MODERATE RISK: MCP Server Coupling
**mcp_server.py shows acceptable but improvable coupling:**

**Current pattern:**
```python
def extract(file: str, compact: bool = False) -> dict:
    if compact:
        from .api import compact_extract
        return compact_extract(file)
    project = str(Path(file).parent)
    return _send_command(project, {"cmd": "extract", "file": file})
```

**Issues:**
1. **Mixed responsibility:** Function handles both local extraction (compact) and daemon delegation (normal)
2. **Asymmetric execution paths:**
   - Compact path: direct function call
   - Normal path: daemon IPC via `_send_command()`
3. **Confusing abstraction:** Tool caller cannot predict whether this is local or remote execution

**Why this is problematic:**
- Daemon path presumably goes through same `extract_file()` eventually
- `compact` flag creates a "local shortcut" that bypasses daemon infrastructure
- If daemon has caching, metrics, or error handling, compact path skips it
- If daemon is down, compact works but normal fails — inconsistent failure modes

**Better alternatives:**
1. **Pass flag to daemon:** `_send_command(project, {"cmd": "extract", "file": file, "compact": compact})`
   - Daemon applies `compact_extract()` wrapper
   - Execution model stays consistent
2. **Always local:** Remove daemon path entirely for `extract()`, use daemon only for project-wide analysis
3. **Document the split:** If intentional, add comment explaining why compact bypasses daemon

**Recommendation:** Option 1 (pass flag to daemon) unless daemon is known to be unavailable for extract operations.

### ✅ CLEAN: Layer Separation
**No cross-layer violations detected:**
- Core API (`api.py`) has no UI dependencies
- CLI (`cli.py`) has no business logic (delegates to API)
- MCP server (`mcp_server.py`) is a thin adapter over API + daemon
- Hooks call CLI, not internal APIs (loose coupling)

---

## 2. Pattern Analysis

### ✅ GOOD: Adapter Pattern in compact_extract()
**Implementation follows classic adapter structure:**
- Adaptee: `extract_file()` (full representation)
- Target interface: compact dict schema (LLM-friendly)
- Adapter logic: field filtering + docstring truncation

**Strengths:**
- Single transformation pass (no repeated dict walking)
- Clear field mapping
- Preserves essential structure (functions, classes, methods hierarchy)

**Potential improvements:**
- **Explicit schema types:** Use `TypedDict` or `dataclass` for `extract_file()` output
  - Would make field dependencies explicit
  - Type checker would catch breakage
- **Shared schema module:** Extract `tldr_swinton.modules.core.schemas` with both full and compact schemas
  - Centralize the "API contract"
  - Easier to version and validate

### ✅ GOOD: Flag-Based Feature Toggle
**CLI `--compact` flag is clean:**
- Boolean flag (simple, no magic values)
- Default `False` (conservative, no surprise behavior change)
- Descriptive help text with concrete benefit ("87% smaller")
- Conditional import keeps default path fast

**Consistency check:**
- Other CLI flags use same pattern (`--with-docs`, `--delta`, etc.)
- No ad-hoc string formats or enums
- Standard argparse conventions

### ⚠️ PATTERN DRIFT: MCP Tool Default Changes
**Changed defaults in `context()` tool:**
```diff
-    format: str = "text",
-    budget: int | None = None,
+    format: str = "ultracompact",
+    budget: int | None = 4000,
```

**Issues:**
1. **Breaking change for existing MCP clients:**
   - Clients relying on `format="text"` will now get `"ultracompact"`
   - Clients expecting unlimited budget will now get 4000 tokens
2. **Inconsistent with CLI defaults:**
   - CLI `context` command likely has different defaults (need to verify)
   - MCP and CLI should share default configuration
3. **No migration path:** Existing prompts/scripts break silently

**Impact severity:**
- **High** if MCP tools are used by external clients (Claude Code plugin consumers)
- **Medium** if only internal use (can update all call sites)
- **Low** if this is pre-1.0 and no stability guarantee exists

**Recommendations:**
1. **If pre-1.0:** Accept the change, document in CHANGELOG as breaking
2. **If stable API:** Revert defaults, use `compact: bool` flag instead (like `extract()`)
3. **Better design:** Introduce `preset` param: `preset="llm-context"` → `format="ultracompact", budget=4000`

### 🔴 ANTI-PATTERN: Fragile Dict Walking
**compact_extract() uses `.get()` chains without validation:**
```python
for f in full.get("functions", []):
    entry: dict = {"name": f["name"], "signature": f["signature"], "line": f["line_number"]}
    if f.get("decorators"):
        entry["decorators"] = f["decorators"]
    if f.get("docstring"):
        entry["doc"] = f["docstring"].split("\n")[0]  # Assumes string, could be None
```

**Problems:**
1. **Silent failures:**
   - If `extract_file()` returns `{"functions": [{"name": "foo"}]}` (missing `signature`), `KeyError` raised
   - If `extract_file()` returns malformed data, no validation until field access
2. **Inconsistent access patterns:**
   - `f["name"]` — crashes if missing (assumed required)
   - `f.get("decorators")` — optional, returns `None` if missing
   - Mixed signals about which fields are required
3. **Assumes string types:**
   - `.split("\n")` assumes `docstring` is `str`, but `extract_file()` might return `None` or other types
   - No guard against `AttributeError`

**Better patterns:**
1. **Defensive extraction:**
   ```python
   signature = f.get("signature")
   if not signature:
       logger.warning(f"Missing signature for function {f.get('name', 'unknown')}")
       continue
   ```
2. **Schema validation:** Use `pydantic`, `marshmallow`, or `TypedDict` + runtime checks
3. **Fail fast:** If required fields missing, raise `ValueError` with context instead of propagating `KeyError`

### ✅ GOOD: Incremental Complexity
**compact_extract() keeps transformation local:**
- No recursive descent into nested structures
- Flattens one level (functions, classes, methods)
- No side effects or global state
- Pure function (same input → same output)

**Avoids common mistakes:**
- No in-place mutation of `full` dict
- No shared mutable defaults
- No hidden configuration dependencies

---

## 3. Simplicity & YAGNI

### ✅ JUSTIFIED: compact_extract() as Separate Function
**Why not a parameter to extract_file()?**

**Current design:**
```python
def extract_file(file_path: str, base_path: str | None = None) -> dict:
    # Full extraction logic

def compact_extract(file_path: str, base_path: str | None = None) -> dict:
    full = extract_file(file_path, base_path)
    # Transform to compact form
```

**Alternative (rejected pattern):**
```python
def extract_file(file_path: str, base_path: str | None = None, compact: bool = False) -> dict:
    # Extract logic
    if compact:
        # Transform
    return result
```

**Why current design is better:**
1. **Single Responsibility:** `extract_file()` has one job (extract), `compact_extract()` has one job (compact)
2. **Composition over flags:** Easier to test, easier to extend (e.g., `ultra_compact_extract()`, `json_extract()`)
3. **No branching inside complex logic:** `extract_file()` stays linear, no conditional output shapes
4. **Clear names:** Function name documents intent better than a boolean flag

**YAGNI check:** Is `compact_extract()` solving a current need or speculative future?
- **Current need:** Hook output is too verbose (stated in commit message)
- **Concrete caller:** `post-read-extract.sh` uses `tldrs extract --compact`
- **Quantified benefit:** "~87% smaller" (measured, not guessed)
- **Verdict:** ✅ Justified, not YAGNI violation

### ⚠️ POTENTIAL OVER-ENGINEERING: Compact Field Selection
**Current implementation strips many fields:**
- Removes `call_graph`, `params`, `is_async`, empty decorators, empty docstrings
- Keeps `name`, `signature`, `line_number`, `decorators` (if present), `docstring` first line

**Question:** Is this the right granularity?

**Missing use-case validation:**
- **Who consumes compact output?** LLM context, but which LLM? Which context window?
- **What fields are actually used?** If LLM never uses `decorators`, why keep them?
- **Is first-line docstring enough?** Or should it be dropped entirely for max compactness?

**Risk of premature optimization:**
- "~87% smaller" is good, but is it solving the right problem?
- If LLM context limit is 8K tokens and current output is 2K tokens, why optimize?
- If problem is "too much noise", field removal might not be the solution (structural summary might be better)

**Recommendations:**
1. **Document compact schema intent:** Add comment listing which fields are essential for LLM context
2. **Track actual token usage:** Measure before/after in real Claude Code sessions
3. **Consider multiple presets:** `--compact`, `--minimal` (signatures only), `--summary` (counts + signatures)

### ✅ CLEAN: Hook Refactoring
**Removed dead code (`suggest-recon.sh`):**
- Never registered in `hooks.json`
- 51 lines of unused complexity
- Removal improves clarity

**Setup hook simplification:**
- Removed `diff-context` execution (moved to `session-start` skill)
- Responsibility split is clear:
  - **Setup hook:** Lightweight project overview (`tldrs structure`)
  - **session-start skill:** Heavy analysis (`tldrs diff-context`)
- Timeout reduced from 10s total to 5s (safe, structure is fast)

**Why this is good:**
1. **Separation of concerns:** Hook provides static info, skill provides dynamic analysis
2. **Timeout safety:** 5s structure call is reliable, 7s diff-context was risky (could fail hook)
3. **Skill can retry:** If session-start fails, Claude Code can recover; if setup hook fails, session is broken

**Potential issue:**
- **Lost context:** If `session-start` skill doesn't run (user opts out, skill disabled), Claude Code gets no diff-context
- **Mitigation:** Document in plugin description that session-start skill is recommended
- **Alternative:** Keep fallback chain in setup hook: `structure → static tip` (already present)

### 🔴 UNNECESSARY COMPLEXITY: Nested Conditionals in compact_extract()
**Current code has 3 levels of conditional logic:**
```python
compact_funcs = []
for f in full.get("functions", []):
    entry: dict = {"name": f["name"], "signature": f["signature"], "line": f["line_number"]}
    if f.get("decorators"):
        entry["decorators"] = f["decorators"]
    if f.get("docstring"):
        entry["doc"] = f["docstring"].split("\n")[0]
    compact_funcs.append(entry)

compact_classes = []
for c in full.get("classes", []):
    cls_entry: dict = {"name": c["name"], "line": c.get("line_number", 0)}
    if c.get("bases"):
        cls_entry["bases"] = c["bases"]
    methods = []
    for m in c.get("methods", []):
        m_entry: dict = {"name": m["name"], "signature": m["signature"], "line": m["line_number"]}
        if m.get("decorators"):
            m_entry["decorators"] = m["decorators"]
        methods.append(m_entry)
    if methods:
        cls_entry["methods"] = methods
    compact_classes.append(cls_entry)
```

**Issues:**
1. **Duplicated transformation logic:**
   - Function entry building appears twice (functions, methods)
   - Same pattern: `{"name": ..., "signature": ..., "line": ...}` + optional decorators
2. **Nested loops are hard to follow:**
   - Class loop contains method loop contains conditional logic
   - 4 levels of indentation
3. **Fragile to schema changes:**
   - Adding a new optional field requires editing 2-3 places

**Better approach (extract helper):**
```python
def _compact_callable(item: dict) -> dict:
    """Extract compact representation of function/method."""
    entry = {
        "name": item["name"],
        "signature": item["signature"],
        "line": item["line_number"]
    }
    if item.get("decorators"):
        entry["decorators"] = item["decorators"]
    return entry

def compact_extract(file_path: str, base_path: str | None = None) -> dict:
    full = extract_file(file_path, base_path)

    result = {
        "file_path": full.get("file_path", file_path),
        "language": full.get("language", "unknown"),
    }

    if funcs := [_compact_callable(f) for f in full.get("functions", [])]:
        # Add first-line docstrings (functions only)
        for f, compact_f in zip(full.get("functions", []), funcs):
            if doc := f.get("docstring"):
                compact_f["doc"] = doc.split("\n")[0]
        result["functions"] = funcs

    if classes := full.get("classes", []):
        compact_classes = []
        for c in classes:
            cls_entry = {"name": c["name"], "line": c.get("line_number", 0)}
            if c.get("bases"):
                cls_entry["bases"] = c["bases"]
            if methods := [_compact_callable(m) for m in c.get("methods", [])]:
                cls_entry["methods"] = methods
            compact_classes.append(cls_entry)
        result["classes"] = compact_classes

    return result
```

**Benefits:**
- Helper function eliminates duplication
- Walrus operator (`:=`) reduces nesting
- Single place to update callable transformation logic
- Clearer intent (helper name documents what it does)

**Trade-off:** Slightly more lines, but much clearer structure.

---

## 4. Missing Architecture Considerations

### 🔴 NO SCHEMA VERSIONING
**Problem:** `compact_extract()` output schema is implicit, not versioned.

**Why this matters:**
- If Claude Code plugin caches compact output, schema changes break cache
- If MCP clients depend on field presence, removals are breaking changes
- No way to detect "this compact output came from old version"

**Recommendations:**
1. **Add schema version to output:**
   ```python
   result = {
       "_schema": "compact_extract_v1",
       "file_path": ...,
       ...
   }
   ```
2. **Document schema in API docs:** List required vs. optional fields
3. **Version the module:** If schema changes, bump `compact_extract_v2()`

### 🔴 NO ERROR HANDLING
**Current code assumes `extract_file()` always succeeds and returns well-formed dict.**

**Missing error cases:**
1. **File not found:** `extract_file()` might raise `FileNotFoundError`
2. **Parse failure:** Malformed Python file might return `{"error": "..."}`
3. **Unsupported language:** Non-Python file might return minimal structure
4. **Schema mismatch:** If `extract_file()` changes, `compact_extract()` might `KeyError`

**Current behavior:** Uncaught exceptions propagate to caller (MCP server, CLI, hook).

**Is this acceptable?**
- **CLI:** User sees traceback (bad UX, but debuggable)
- **MCP server:** Client sees JSON-RPC error (acceptable for tool calls)
- **Hook:** Hook fails, Claude Code shows "hook error" (bad, breaks session setup)

**Recommendations for hooks:**
1. **Wrap in try/except:** `post-read-extract.sh` should catch failures and return empty JSON
2. **Timeout is not enough:** `timeout 5 tldrs extract --compact` kills on timeout, but doesn't catch parse errors
3. **Graceful degradation:** If extract fails, return `{"status": "extract_failed", "file": "..."}` instead of blocking hook

### 🔴 NO TESTING ADDITIONS VISIBLE
**Changed code has no corresponding test updates in diff.**

**Critical test cases missing (or not shown):**
1. **compact_extract() output schema:**
   - Test that required fields are present
   - Test that omitted fields are actually omitted
   - Test that token count is ~87% smaller (regression test)
2. **CLI --compact flag:**
   - Test that flag triggers `compact_extract()` import
   - Test that default path still uses `extract_file()`
3. **MCP server compact parameter:**
   - Test that `extract(..., compact=True)` returns compact schema
   - Test that `extract(..., compact=False)` returns full schema
4. **Hook integration:**
   - Test that `tldrs extract --compact` output fits in hook output limits
   - Test that hook succeeds even if extract times out

**Without tests, this change is fragile:**
- Schema drift will go unnoticed
- Token savings claim ("~87%") is unverified
- Refactoring `extract_file()` might break `compact_extract()` silently

---

## 5. Scope & Ownership

### ✅ CLEAN: Single Feature Scope
**Change touches exactly what's needed for compact extract:**
- API layer: add `compact_extract()`
- CLI layer: add `--compact` flag
- MCP layer: add `compact` param
- Hook layer: switch to `--compact`
- Docs: update AGENTS.md

**No scope creep detected:**
- No unrelated refactoring
- No "while I'm here" fixes
- No premature optimization elsewhere

### ⚠️ SCOPE CREEP: MCP context() Default Changes
**Unrelated change bundled into this diff:**
```diff
-    format: str = "text",
-    budget: int | None = None,
+    format: str = "ultracompact",
+    budget: int | None = 4000,
```

**Why this is scope creep:**
- Not part of "compact extract" feature
- Affects different tool (`context()` not `extract()`)
- Breaking change to existing behavior
- No mention in commit message

**Should be separate commit:**
- Title: "feat(mcp): change context() defaults for LLM consumption"
- Body: Explain why `ultracompact` + `budget=4000` is better default
- Allows independent review and revert if needed

### ✅ CLEAR OWNERSHIP: Hook Responsibility Split
**Before:** Setup hook tried to run diff-context (heavy, risky)
**After:** Setup hook runs structure (lightweight, reliable)
**Reason:** session-start skill now owns diff-context execution

**Ownership boundaries:**
- **Setup hook:** Project metadata (language, structure, git status)
- **session-start skill:** Task-specific analysis (diff-context)
- **post-read-extract hook:** File-level detail (compact extract)

**Why this is clean:**
- Each hook has single responsibility
- Timeouts are appropriate to responsibility (5s for structure, 10s for setup)
- Skills can fail without breaking session (hooks cannot)

---

## 6. Integration Risks

### ⚠️ MODERATE RISK: Hook Timeout Assumptions
**post-read-extract.sh uses `timeout 5`:**
```bash
EXTRACT_OUTPUT=$(timeout 5 tldrs extract --compact "$FILE" 2>/dev/null)
```

**Assumptions:**
1. `tldrs extract --compact` completes in <5s for typical files
2. If timeout triggers, hook returns empty output (graceful)
3. Claude Code doesn't cache failed hook output

**What if file is large?**
- 5000-line Python file might take >5s to parse
- `timeout` kills process, hook returns empty
- Claude Code proceeds without structure info (degraded but not broken)

**What if file is binary?**
- `extract` might crash or hang on non-text files
- `2>/dev/null` suppresses error, hook returns empty
- Same degraded outcome

**Recommendations:**
1. **Pre-filter file types:** Check extension before running extract
   ```bash
   if [[ "$FILE" =~ \.(py|ts|js|go|rs)$ ]]; then
       EXTRACT_OUTPUT=$(timeout 5 tldrs extract --compact "$FILE" 2>/dev/null)
   fi
   ```
2. **Adjust timeout by file size:** `timeout $((5 + $(wc -l < "$FILE") / 1000))` (5s + 1s per 1000 lines)
3. **Log failures:** Append failed extracts to `~/.tldrs/hook-failures.log` for debugging

### 🔴 HIGH RISK: MCP Server Daemon Bypass
**As noted in section 1, compact path bypasses daemon:**
```python
if compact:
    from .api import compact_extract
    return compact_extract(file)
# Normal path goes through daemon
return _send_command(project, {"cmd": "extract", "file": file})
```

**What breaks:**
1. **Caching:** If daemon caches `extract_file()` results, compact calls miss cache
2. **Metrics:** Daemon might track tool usage; compact calls are invisible
3. **Rate limiting:** Daemon might throttle expensive operations; compact bypasses throttles
4. **Consistency:** Daemon might normalize file paths, apply project-specific config; compact skips this

**Fix priority:** **HIGH** — this is an architectural inconsistency that will cause subtle bugs.

**Recommended fix:**
```python
def extract(file: str, compact: bool = False) -> dict:
    """Extract full code structure from a file.

    Returns imports, functions, classes, and intra-file call graph.

    Args:
        file: Path to source file
        compact: If True, return signatures and line numbers only (~87% smaller).
    """
    project = str(Path(file).parent)
    return _send_command(project, {"cmd": "extract", "file": file, "compact": compact})
```

Then update daemon to handle `compact` flag internally.

---

## 7. Recommendations Summary

### Must Fix (Architectural Integrity)
1. **MCP daemon bypass:** Pass `compact` flag to daemon instead of local shortcut
2. **Schema validation:** Add runtime checks for required fields in `compact_extract()`
3. **Separate commits:** Split MCP `context()` default changes into own commit

### Should Fix (Maintainability)
4. **Extract helper function:** `_compact_callable()` to eliminate duplication
5. **Error handling:** Wrap `compact_extract()` in try/except for hook use
6. **Add tests:** Verify output schema, token savings, flag behavior

### Consider (Long-term)
7. **Schema versioning:** Add `_schema` field to compact output
8. **Pre-filter hook files:** Check extension before running extract
9. **Document compact schema:** List required vs. optional fields in docstring
10. **Multiple presets:** `--compact`, `--minimal`, `--summary` instead of one size fits all

### Optional (Code Quality)
11. **Use TypedDict:** Define schemas for `extract_file()` and `compact_extract()` output
12. **Consistent defaults:** Align MCP and CLI default behavior
13. **Timeout scaling:** Adjust hook timeout based on file size

---

## 8. Final Verdict

### Structural Quality: **B+ (Good with reservations)**

**Strengths:**
- Clean module boundaries (API, CLI, MCP, hooks)
- Single responsibility functions
- No cross-layer violations
- Removed dead code (suggest-recon.sh)
- Clear hook responsibility split

**Weaknesses:**
- MCP daemon bypass creates inconsistent execution paths
- Fragile dict walking without schema validation
- Scope creep (MCP context() defaults bundled in)
- Nested conditionals with duplicated transformation logic
- Missing error handling for hook robustness

**Complexity Assessment:**
- `compact_extract()`: **Acceptable** — linear transformation, no hidden state
- Hook changes: **Good** — simplified, clear ownership
- MCP server: **Problematic** — mixed local/remote execution model

**YAGNI Compliance:**
- Feature is justified (concrete use case, measured benefit)
- Field selection might be over-engineered (no validation of which fields are essential)
- No premature abstractions introduced

**Critical Fix Required:**
- MCP `extract()` daemon bypass must be resolved before merging
- This creates a maintenance burden and will cause bugs

**Recommended Merge Decision:**
- ✅ Merge after fixing MCP daemon bypass
- ✅ Add schema validation and error handling
- ✅ Split MCP context() defaults into separate commit
- ⚠️ Without fixes, accept risk of subtle daemon-related bugs
