# Agent-Native Architecture Review: ColBERT Backend Implementation

**Date:** 2026-02-14
**Reviewer:** Claude Code (Agent-Native Architecture Specialist)
**Scope:** ColBERT backend implementation - agent-native parity check

## Summary

The ColBERT backend implementation suffers from **critical agent-native gaps**. While users can choose the ColBERT backend via CLI (`tldrs semantic index --backend=colbert`), MCP-connected agents have **NO ABILITY** to select backends, rebuild indexes, or query backend status. The semantic search functionality is partially agent-accessible but missing all management/administrative capabilities.

**Verdict:** NEEDS WORK (3/7 capabilities agent-accessible)

---

## Capability Map

| UI/CLI Action | Location | MCP Tool | Prompt Ref | Status |
|---------------|----------|----------|------------|--------|
| **Build index with backend choice** | cli.py:1664-1676 | ❌ None | ❌ None | ❌ CRITICAL |
| **Search semantic index** | cli.py:1678-1680 | ✅ `semantic()` | ✅ mcp_server.py:429-442 | ✅ PASS |
| **Rebuild existing index** | cli.py:1668 (`rebuild` param) | ❌ None | ❌ None | ❌ CRITICAL |
| **Query index info/stats** | `get_index_info()` | ⚠️ Partial via `status()` | ⚠️ Incomplete | ⚠️ DEGRADED |
| **Switch backend (FAISS → ColBERT)** | cli.py:1667 (`--backend` flag) | ❌ None | ❌ None | ❌ CRITICAL |
| **View backend in use** | Search results | ⚠️ Indirect (`semantic()` result) | ⚠️ Not in docs | ⚠️ HIDDEN |
| **Trigger incremental update** | cli.py:1664-1675 (auto-detects changes) | ❌ None | ❌ None | ❌ MISSING |

**Score:** 1 full pass, 2 partial/degraded, 4 critical failures = **3/7 capabilities agent-accessible**

---

## Critical Issues (Must Fix)

### P1: MCP `semantic()` Tool Missing Backend Parameter

**Location:** `src/tldr_swinton/modules/semantic/mcp_server.py:434-442`

**Current signature:**
```python
@mcp.tool(description="Semantic code search using embeddings...")
def semantic(
    project: str,
    query: str,
    k: int = 10,
) -> dict:
    return _send_command(
        project, {"cmd": "semantic", "action": "search", "query": query, "k": k}
    )
```

**Problem:**
- CLI users can do: `tldrs semantic index --backend=colbert`
- MCP agents CANNOT choose backends — no `backend` parameter exists
- Agents stuck with whatever backend was last used, or factory auto-selection
- **Impact:** If user manually builds FAISS index, agent can't upgrade to ColBERT without user CLI intervention

**Fix:**
Add `backend` and `action` parameters to `semantic()` tool:

```python
@mcp.tool(description="Semantic code search and index management using embeddings...")
def semantic(
    project: str,
    query: str | None = None,
    action: Annotated[str, Field(description="'search' or 'index'")] = "search",
    backend: Annotated[str | None, Field(description="Backend: 'auto', 'colbert', 'faiss' (index action only)")] = None,
    k: int = 10,
    rebuild: bool = False,
) -> dict:
    """Semantic code search and index building."""
    cmd = {"cmd": "semantic", "action": action}

    if action == "index":
        if backend is not None:
            cmd["backend"] = backend
        cmd["rebuild"] = rebuild
        # index doesn't need query
    else:
        if query is None:
            raise ValueError("query required for search action")
        cmd["query"] = query
        cmd["k"] = k

    return _send_command(project, cmd)
```

**OR** (cleaner): Split into two separate tools:

```python
@mcp.tool(description="Search code by meaning using embeddings...")
def semantic_search(project: str, query: str, k: int = 10) -> dict:
    """Semantic code search (existing behavior)."""
    return _send_command(
        project, {"cmd": "semantic", "action": "search", "query": query, "k": k}
    )

@mcp.tool(description="Build or rebuild semantic index. Choose backend: 'auto', 'colbert', or 'faiss'.")
def semantic_index(
    project: str,
    backend: Annotated[str, Field(description="Backend: 'auto' (prefer ColBERT), 'colbert', or 'faiss'")] = "auto",
    rebuild: Annotated[bool, Field(description="Force full rebuild instead of incremental update")] = False,
    language: Annotated[str | None, Field(description="Language filter (python, typescript, etc.)")] = None,
) -> dict:
    """Build or update semantic index for a project."""
    cmd = {"cmd": "semantic", "action": "index", "backend": backend, "rebuild": rebuild}
    if language:
        cmd["language"] = language
    return _send_command(project, cmd)
```

**Recommended:** **Split into two tools** — cleaner API, better discoverability, aligns with CLI's two subcommands.

---

### P1: Daemon Missing Backend Parameter in `_handle_semantic()`

**Location:** `src/tldr_swinton/modules/core/daemon.py:588-638`

**Current code:**
```python
def _handle_semantic(self, command: dict) -> dict:
    action = command.get("action", "search")
    try:
        if action == "index":
            from ..semantic.index import build_index
            language = command.get("language", "python")
            backend = command.get("backend", "auto")  # ← READS backend param
            stats = build_index(
                str(self.project), language=language, backend=backend,
            )
            # Invalidate cached backend
            self._semantic_backend = None
            return {"status": "ok", "indexed": stats.total_units}
```

**Problem:**
- Daemon already reads `backend` parameter from command dict (line 600)
- But MCP tool doesn't send it! (See P1 above)
- **Impact:** Backend selection works in daemon, just needs MCP plumbing

**Fix:** Already implemented correctly in daemon. Just needs MCP tool updated (see P1 fix).

---

### P1: No Tool to Query Index Metadata

**Location:** Missing from `mcp_server.py`

**Problem:**
- CLI users can infer backend via search results (includes `"backend": "colbert"` field)
- Agents can see backend in search results BUT don't know:
  - What backend is configured before searching
  - Index stats (total units, dimension, model name)
  - Whether an index exists at all (must search and catch error)
  - Storage location, size
- `get_index_info()` exists in `index.py` but has NO MCP TOOL

**Impact:**
Agents can't answer: "What semantic backend is this project using?" without running a dummy search.

**Fix:**
Add `semantic_info()` tool:

```python
@mcp.tool(description="Get semantic index metadata — backend, model, size, storage path.")
def semantic_info(
    project: Annotated[str, Field(description="Project root directory")] = ".",
) -> dict:
    """Get semantic index information."""
    from .index import get_index_info

    info = get_index_info(project)
    if info is None:
        return {"status": "no_index", "message": "No semantic index found. Run semantic_index() first."}

    return {
        "status": "ok",
        "backend": info["backend"],
        "model": info["embed_model"],
        "count": info["count"],
        "dimension": info["dimension"],
        "index_path": info["index_path"],
        **info.get("extra", {}),
    }
```

---

### P1: System Prompt Missing Backend Capabilities

**Location:** `mcp_server.py:33-44` (`_INSTRUCTIONS`)

**Current prompt:**
```python
_INSTRUCTIONS = """\
tldr-code provides token-efficient code reconnaissance. Use these tools INSTEAD OF \
Read/Grep/Glob when you need to understand code structure without reading full files.

COST LADDER (cheapest first):
1. extract(file, compact=True) ~200 tok — file map. Use INSTEAD OF Read for overview.
2. structure(project) ~500 tok — directory symbols. Use INSTEAD OF Glob + multiple Reads.
3. context(entry) ~400 tok — call graph around symbol. Use INSTEAD OF reading caller files.
4. diff_context(project) ~800 tok — changed-code context. Use INSTEAD OF git diff + Read.
5. impact(function) ~300 tok — reverse call graph. Use BEFORE refactoring any function.
6. semantic(query) ~300 tok — meaning-based search. Use INSTEAD OF Grep for concepts.\
"""
```

**Problem:**
- No mention of backend choice (`--backend=colbert` for best quality)
- No guidance on when to rebuild index
- No mention of `semantic_info()` tool (once added)
- Agents don't know ColBERT exists or why to prefer it

**Fix:**
Update prompt to include backend guidance:

```python
_INSTRUCTIONS = """\
tldr-code provides token-efficient code reconnaissance. Use these tools INSTEAD OF \
Read/Grep/Glob when you need to understand code structure without reading full files.

COST LADDER (cheapest first):
1. extract(file, compact=True) ~200 tok — file map. Use INSTEAD OF Read for overview.
2. structure(project) ~500 tok — directory symbols. Use INSTEAD OF Glob + multiple Reads.
3. context(entry) ~400 tok — call graph around symbol. Use INSTEAD OF reading caller files.
4. diff_context(project) ~800 tok — changed-code context. Use INSTEAD OF git diff + Read.
5. impact(function) ~300 tok — reverse call graph. Use BEFORE refactoring any function.
6. semantic(query) ~300 tok — meaning-based search. Use INSTEAD OF Grep for concepts.

SEMANTIC BACKENDS:
- Use semantic_info() to check current backend and index stats
- ColBERT backend (best quality): semantic_index(backend="colbert")
- FAISS backend (lightweight fallback): semantic_index(backend="faiss")
- Auto-select (prefer ColBERT): semantic_index(backend="auto")
- Rebuild after major refactors: semantic_index(rebuild=True)
"""
```

---

## Warnings (Should Fix)

### P2: No Incremental Update Trigger for Agents

**Location:** CLI triggers via `build_index()` with auto file-hash change detection

**Problem:**
- CLI: Running `tldrs semantic index` automatically detects changed files, does incremental update
- Agents: Must pass `rebuild=False` (default) to get incremental behavior
- BUT: Agents have no way to know IF incremental update is needed
- No "dirty flag" check exposed via MCP

**Impact:**
Agents will either:
1. Over-index (rebuild too often, wasting time)
2. Under-index (forget to update after code changes, stale results)

**Recommendation:**
Add `semantic_dirty_check()` tool:

```python
@mcp.tool(description="Check if semantic index needs updating based on file changes.")
def semantic_dirty_check(
    project: Annotated[str, Field(description="Project root directory")] = ".",
) -> dict:
    """Check if semantic index is out of date."""
    from .index import get_index_info
    from ..core.dirty_flag import is_dirty, get_dirty_files

    info = get_index_info(project)
    if info is None:
        return {"status": "no_index", "needs_update": True, "reason": "No index exists"}

    project_path = Path(project).resolve()
    if is_dirty(project_path):
        dirty = get_dirty_files(project_path)
        return {
            "status": "dirty",
            "needs_update": True,
            "dirty_files": dirty,
            "reason": f"{len(dirty)} files changed since last index",
        }

    return {"status": "clean", "needs_update": False}
```

Agents can then: check dirty → if dirty, call `semantic_index(rebuild=False)`.

---

### P2: Search Results Include Backend but Not Documented

**Location:** `mcp_server.py:434-442`, `daemon.py:620-630`

**Current behavior:**
Search results include `"backend": "colbert"` or `"backend": "faiss"` field per result.

**Problem:**
- Field is present in output BUT
- Not mentioned in tool description
- Not mentioned in system prompt
- Agents won't know to check it

**Fix:**
Update `semantic()` tool description:

```python
@mcp.tool(description=(
    "Search code by meaning using embeddings. ~300 tokens. "
    "Finds related functions/classes even without exact keywords. "
    "Use INSTEAD OF Grep when searching for a concept rather than literal text. "
    "Results include 'backend' field showing which search backend was used (colbert or faiss)."
))
def semantic(...):
```

---

### P2: No Guidance on When to Use ColBERT vs FAISS

**Location:** Missing from docs, CLI help text, and MCP prompt

**Problem:**
- Plan doc says "ColBERT preferred when available" but user-facing docs don't explain WHY
- No quality benchmarks shared
- No guidance on when FAISS is "good enough"
- Agents and users don't know: "Should I spend 17s loading ColBERT model?"

**Recommendation:**
Add to AGENTS.md and CLI `--help` output:

```
Semantic Search Backends:

- **ColBERT** (best quality, ~1.7GB install, ~17s cold start):
  - Multi-vector late interaction — understands code semantics better
  - Preferred for: large codebases, unfamiliar code, concept search
  - Install: pip install 'tldr-swinton[semantic-colbert]'

- **FAISS** (lightweight, ~100MB install, <1s cold start):
  - Single-vector embeddings via Ollama or sentence-transformers
  - Good for: smaller projects, exact identifier search, low-memory envs
  - Install: pip install 'tldr-swinton[semantic-ollama]'

Auto-selection: Prefers ColBERT if installed, falls back to FAISS.
```

---

## Observations (Consider)

### O1: Backend Switch is Destructive (No Migration Path)

**Observation:**
Switching from FAISS → ColBERT requires full rebuild:
```bash
tldrs semantic index --backend=colbert  # Rebuilds from scratch
```

Old FAISS index data is overwritten (same `.tldrs/index/` dir).

**Consideration:**
Should backends use separate index dirs to allow side-by-side comparison?

```
.tldrs/index/
├── faiss/      # FAISS index + meta.json
└── colbert/    # ColBERT plaid/ + meta.json
```

Then `get_backend(backend="auto")` reads from active symlink or config file.

**Pros:**
- Users can A/B test backends without losing data
- Rollback if ColBERT causes issues
- Agent can trigger "compare search quality" benchmarks

**Cons:**
- 2x storage (not huge — ~5-6KB per code unit for ColBERT vs 3KB for FAISS)
- Extra complexity in auto-detection

**Verdict:** Defer to post-MVP. Current design is simpler.

---

### O2: Model Loading Feedback Only in Daemon Logs

**Observation:**
Plan requires logging: `"Loading ColBERT model (first query only, ~17s)..."`

Daemon logs this, but:
- MCP agents don't see daemon logs (stdio hijacked by MCP protocol)
- First agent semantic search appears to hang for 17s with no feedback

**Consideration:**
Add progress indicator to MCP tool response during first load:

```python
def semantic(project, query, k=10):
    result = _send_command(project, {"cmd": "semantic", ...})

    # If result includes "cold_start": true, agent knows why it was slow
    if result.get("cold_start"):
        result["info"] = "First query loaded ColBERT model (~17s). Subsequent queries <10ms."

    return result
```

Daemon would need to track `_first_semantic_query` flag and set `"cold_start": true` in response.

**Verdict:** Nice-to-have. Not blocking.

---

## Recommendations

### Immediate (Before Merge)

1. **[P1] Add `semantic_index()` MCP tool** — agents must be able to build/rebuild indexes with backend choice
2. **[P1] Add `semantic_info()` MCP tool** — agents need index metadata (backend, model, count, path)
3. **[P1] Update system prompt** — document backend options and when to use them
4. **[P2] Document `backend` field** — update `semantic()` tool description to mention result field
5. **[P2] Add backend guidance to AGENTS.md** — explain ColBERT vs FAISS tradeoffs

### Post-MVP Enhancements

6. **[P2] Add `semantic_dirty_check()` tool** — let agents know when incremental update needed
7. **[O1] Consider separate index dirs per backend** — enable A/B testing, safer rollback
8. **[O2] Add cold-start feedback** — first-query latency transparency for agents

---

## What's Working Well

1. **Backend abstraction is solid** — `SearchBackend` protocol cleanly separates FAISS/ColBERT, easy to extend
2. **Daemon caching works** — model stays resident after first load, subsequent queries fast
3. **Auto-detection logic** — factory reading `meta.json` prevents accidental backend mismatch
4. **Incremental updates** — file hash comparison avoids re-indexing unchanged code
5. **Search quality field** — including `"backend"` in results is good transparency
6. **Graceful fallback** — if pylate missing, auto falls back to FAISS (no hard failure)

---

## Agent-Native Score

**Current state:**
- ✅ Agents can search (via `semantic()` tool)
- ❌ Agents CANNOT choose backend
- ❌ Agents CANNOT rebuild index
- ❌ Agents CANNOT query index metadata
- ⚠️ Agents see backend in results but it's undocumented
- ❌ Agents have no dirty-check for incremental updates

**Action Parity:** 1/6 capabilities (search only)
**Context Parity:** Partial (backend visible but not explained)
**Shared Workspace:** ✅ Pass (agents and users use same `.tldrs/index/`)
**Primitives over Workflows:** ✅ Pass (`semantic()` is a primitive query, not encoded logic)
**Dynamic Context Injection:** ❌ Fail (no backend guidance in system prompt)

**Overall Verdict:** **NEEDS WORK**

Blocking issues:
- P1: Add `semantic_index()` tool
- P1: Add `semantic_info()` tool
- P1: Update MCP system prompt with backend guidance

With these fixes, score improves to **5/6 capabilities** (near-parity).

---

## Appendix: Relevant Code Locations

| Component | File | Lines |
|-----------|------|-------|
| CLI backend flag | `cli.py` | 759-763, 1667 |
| CLI search | `cli.py` | 1678-1680 |
| Daemon semantic handler | `daemon.py` | 588-638 |
| MCP semantic tool | `mcp_server.py` | 434-442 |
| MCP system prompt | `mcp_server.py` | 33-44 |
| Backend factory | `backend.py` | 169-223 |
| Build index | `index.py` | 303-389 |
| Search index | `index.py` | 421-499 |
| Get index info | `index.py` | 531-551 |

---

## Review Metadata

- **Reviewer:** Claude Code (Agent-Native Architecture Review Specialist)
- **Review Type:** Agent-Native Parity Check
- **Scope:** ColBERT backend MCP integration
- **Date:** 2026-02-14
- **Bead:** tldr-swinton-wp7
- **Related Plan:** `docs/plans/2026-02-14-colbert-search-backend.md`
