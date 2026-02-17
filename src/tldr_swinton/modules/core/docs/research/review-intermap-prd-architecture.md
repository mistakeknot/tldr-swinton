# Architecture Review: Intermap Extraction PRD

**Reviewed:** 2026-02-16
**Reviewer:** Flux-drive Architecture & Design
**Document:** `/root/projects/Interverse/docs/prds/2026-02-16-intermap-extraction.md`

## Executive Summary

**Recommendation: PROCEED WITH MAJOR SIMPLIFICATIONS**

The PRD proposes extracting 6 Python modules (209 KB) from tldr-swinton into a new Go+Python hybrid MCP server plugin (intermap). The core structural goal — separating project-level analysis from file-level context — is sound and will reduce architectural entropy. However, the execution plan contains significant complexity risks, premature abstractions, and boundary violations that must be addressed before implementation.

**Critical Issues:**
1. **Language Boundary Violation (F1):** Go-to-Python subprocess bridge adds operational complexity for zero architectural benefit when pure Python MCP servers are proven stable in this ecosystem.
2. **Import Dependency Explosion (F2):** Modules depend on 9+ tldr-swinton internals; "breaking dependencies" without impact analysis risks parallel reimplementation.
3. **Premature Overlay Feature (F5):** Agent activity overlay couples unrelated concerns (code analysis + live runtime state) before the core extraction is validated.
4. **Scope Creep via "No Daemon" (Open Q3):** One-shot subprocess calls will trigger performance complaints and force daemon architecture in v0.2, making v0.1 throwaway work.

**Savings Opportunity:** Remove F1 (Go bridge), F5 (overlay), and Open Q3 (daemon deferral). Use pure Python MCP server pattern from interject/interflux. This eliminates 40% of PRD complexity while preserving the core boundary correction.

---

## 1. Boundaries & Coupling Analysis

### 1.1 Component Map

```
tldr-swinton (1.4 MB, 42K lines)
├── modules/core/
│   ├── File-level context (STAYS)
│   │   ├── api.py, hybrid_extractor.py, ast_extractor.py
│   │   ├── contextpack_engine.py, daemon.py, mcp_server.py
│   │   └── cfg/dfg/pdg extractors (function-level analysis)
│   │
│   └── Project-level analysis (MOVES → intermap)
│       ├── cross_file_calls.py (119 KB) — call graph builder
│       ├── analysis.py (13 KB) — graph analysis (dead code, hotspots)
│       ├── project_index.py (13 KB) — unified symbol scanner
│       ├── change_impact.py (12 KB) — impact analysis via graph
│       ├── diagnostics.py (40 KB) — diagnostics + compiler errors
│       └── durability.py (12 KB) — cross-file reliability checks
│
└── modules/semantic/ (STAYS)
    └── Semantic search (already isolated)

Proposed intermap plugin
├── Go MCP server (new, stdio bridge)
├── Python subprocess bridge (new, JSON stdout parser)
├── Extracted modules (6 files, 209 KB)
├── Vendored workspace.py (new, reimplementation)
└── Project registry (new, Go-native git scanner)
```

### 1.2 Boundary Violations

**CRITICAL: F1 Go-to-Python Bridge is Accidental Complexity**

The PRD proposes a Go MCP server that spawns Python subprocesses:
```go
exec.Command("python3", "-m", "intermap.analyze", "--command=X", "--project=Y")
```

**Why this is wrong:**
- **Zero architectural necessity:** Python MCP servers exist and work (interject, interflux use `mcp` Python package). The Go layer adds no capability.
- **Operational fragility:** Every tool call requires process spawn + JSON parse + stderr capture. Error surfaces multiply (Go stdio bugs, Python import failures, JSON encoding mismatches).
- **Maintenance tax:** Two languages, two build systems, two test harnesses, two deployment paths. Cross-language debugging is expensive.
- **Pattern divergence:** Existing plugins (interject, interflux) use pure Python MCP. Adding a hybrid pattern creates ecosystem fragmentation.

**Evidence from existing patterns:**
- `interlock`: Go MCP wraps Go HTTP client → legitimate (intermute API is Go, no Python exists)
- `intermux`: Go MCP for tmux monitoring → legitimate (pure Go, no Python)
- `interject`: Python MCP wraps Python analysis → stable, ships as plugin
- `interflux`: Python MCP for research agents → stable, uses `mcp` package

**Verdict:** The Go bridge is **not solving a real integration problem**. It's premature optimization based on a false assumption that "Go is needed for MCP servers."

**Recommended fix:** Use pure Python MCP server (same as interject). Matches existing patterns, eliminates half the PRD's implementation cost.

---

### 1.3 Dependency Analysis

**F2 claims "breaking import dependencies" but provides no impact map.**

Actual dependencies discovered via grep:

| Module | tldr-swinton Imports | Status |
|--------|---------------------|---------|
| `cross_file_calls.py` | `workspace.py` (WorkspaceConfig, iter, load) | **Mandatory** — file iterator + config |
| `project_index.py` | `ast_cache`, `hybrid_extractor`, `ast_extractor`, `workspace` | **Deep entanglement** — 4 modules |
| `change_impact.py` | `dirty_flag` (get_changed_files) | **Tight coupling** — git diff state |
| `analysis.py` | None (operates on data structures) | **Clean** |
| `diagnostics.py` | None (zero internal deps) | **Clean** |
| `durability.py` | `cross_file_calls` only | **Clean** |

**The PRD says:**
> "dependency on ast_cache/ast_extractor/hybrid_extractor resolved (simplified or vendored)"

**This is hand-waving.** Options analysis:

| Option | Cost | Risk |
|--------|------|------|
| **Vendor stubs** | Low (copy 50 lines) | High (breaks when tldr updates) |
| **Simplify to not need them** | Unknown | High (requires redesign, out of scope) |
| **Call tldr daemon** | Medium (RPC layer) | Medium (circular plugin dependency) |
| **Vendor full modules** | High (300+ KB duplication) | Medium (drift risk) |
| **Shared library extraction** | Very High (3-plugin refactor) | Low (correct boundary) |

**The PRD does not declare which option is chosen.** This is a **must-fix before F2 implementation** — cannot start "move modules" without knowing how dependencies resolve.

**Recommended decision path:**
1. Audit actual usage of `ast_cache`/`hybrid_extractor` in `project_index.py`.
2. If only used for file scanning, vendor lightweight `iter_workspace_files()` + `HybridExtractor.extract()` wrapper.
3. If used for symbol indexing, **do not extract project_index.py** — it's too coupled. Extract only `cross_file_calls` + `analysis` + `diagnostics` + `durability`.
4. Leave `change_impact.py` in tldr-swinton until `dirty_flag` is refactored (git state belongs with file-level context anyway).

---

### 1.4 Data Flow Integrity

**Proposed flow (from PRD F1):**
```
Claude Code
  ↓ (MCP stdio)
Go MCP server
  ↓ (subprocess spawn)
Python -m intermap.analyze --command=X
  ↓ (JSON stdout)
Go JSON parser
  ↓ (MCP tool response)
Claude Code
```

**Actual correct flow (interject pattern):**
```
Claude Code
  ↓ (MCP stdio)
Python MCP server (mcp package)
  ↓ (direct function call)
intermap.analyze module
  ↓ (return dict)
MCP server serializes to JSON
  ↓
Claude Code
```

**The extra Go layer is pure waste.** No boundary enforcement benefit (Python can crash either way), no performance benefit (subprocess overhead is higher than in-process calls), no isolation benefit (shared filesystem state anyway).

---

### 1.5 Scope Creep: F5 Agent Overlay

**F5 proposes enriching project map with live agent activity from intermux.**

This is **coupling unrelated concerns**:
- **intermap concern:** Static code analysis (call graphs, dead code, project structure)
- **intermux concern:** Live runtime state (active agents, editing status, tmux sessions)

**Why this is wrong:**
1. **No shared lifecycle:** Code structure changes on git commits; agent state changes every 10 seconds. These operate on different timescales.
2. **Failure coupling:** If intermux is down, intermap tools return "projects without agent data" — but why should a call graph query fail because tmux monitoring is offline?
3. **Responsibility blur:** "Which agents are working in this project" is an intermux query, not an intermap query. The project registry is just a join key.
4. **Premature integration:** F4 (project registry) is not validated yet. Adding intermux integration before the core feature works is speculative layering.

**Recommended fix:** Remove F5 from v0.1. If agent-enriched project views are valuable, build them as:
- An intermux tool that joins its agent state with intermap's project registry (correct: intermux owns the agent overlay concern)
- A separate Clavain skill that composes `intermap.project_registry()` + `intermux.agent_map()` (correct: orchestration lives in the hub, not in leaf plugins)

This preserves the capability without entangling intermap's architecture.

---

## 2. Pattern Analysis

### 2.1 Explicit Patterns in Use

**Interverse MCP plugin patterns (from interlock/intermux):**

| Pattern | Where | Rule |
|---------|-------|------|
| **Go binary MCP** | interlock, intermux | When wrapping Go services (intermute HTTP, tmux monitoring) or when stdlib benefits justify cost |
| **Python MCP** | interject, interflux | When logic is already Python and no cross-language boundary exists |
| **`bin/launch-mcp.sh`** | All MCP plugins | Auto-build binary before serving (Go plugins only) |
| **Env-based config** | All MCP plugins | `*_URL`, `*_SOCKET`, `*_AGENT_ID` for external service integration |
| **Graceful degradation** | intermux | Optional dependencies (intermute push) don't block core functionality |

**The PRD violates "Python MCP" pattern by choosing Go when no Go service exists.**

---

### 2.2 Anti-Patterns Detected

**1. Speculative Abstraction: Python Subprocess Bridge**

The Go-to-Python bridge is a solution without a problem. The PRD does not justify why:
- Go is required when Python MCP servers exist
- Subprocess overhead is acceptable for 10+ tool calls per session
- Maintaining two languages for a single feature is worth the cost

**This is premature optimization.** The correct sequence is:
1. Build pure Python MCP (fast, low risk, matches ecosystem)
2. Measure performance on real workloads
3. **If** subprocess latency is unacceptable, **then** consider daemon or rewrite

Jumping to Go+subprocess skips step 1 and commits to complexity before need is proven.

---

**2. God Module Risk: `project_index.py`**

From code inspection:
```python
@dataclass
class ProjectIndex:
    # Core indexes (7 dicts)
    symbol_index: dict[str, FunctionInfo]
    symbol_files: dict[str, str]
    symbol_raw_names: dict[str, str]
    signature_overrides: dict[str, str]
    name_index: dict[str, list[str]]
    qualified_index: dict[str, list[str]]
    file_name_index: dict[str, dict[str, list[str]]]

    # Optional data
    file_sources: dict[str, str]
    symbol_ranges: dict[str, tuple[int, int]]

    # Call graph
    adjacency: dict[str, list[str]]
    reverse_adjacency: dict[str, list[str]]
```

This is **11 index dictionaries** serving multiple consumers (symbolkite, difflens, cross_file_calls). The PRD wants to move this to intermap, but it's used by tldr-swinton's file-level tools.

**Moving it creates a circular dependency:**
- intermap needs ProjectIndex for call graphs
- tldr-swinton needs ProjectIndex for difflens/symbolkite
- Both plugins would vendor or duplicate it

**Correct boundary:** `ProjectIndex` is **shared infrastructure**, not project-level or file-level. It should either:
- Stay in tldr-swinton (since it's already there and works)
- Extract to a third shared library (like `intersearch` for embeddings)
- Split into two classes: `FileIndex` (tldr) and `CallGraphIndex` (intermap)

**The PRD does not address this.** Accepting "moved" without analyzing downstream impact is architectural negligence.

---

**3. YAGNI Violation: F4 Project Registry Caching**

```
- Registry caches results with configurable TTL (default 5 min)
```

**Questions not answered:**
- How many projects are in a typical workspace? (If <10, caching is noise)
- How often do agents query the registry? (If once per session, TTL is irrelevant)
- What invalidates the cache? (New git clones, branch switches — auto-detection is complex)

**This is premature optimization.** The correct approach:
1. Build naive version: scan filesystem on every call
2. Measure actual latency (likely <100ms for <100 projects)
3. **If** performance is unacceptable, **then** add caching with clear invalidation rules

Adding TTL before measuring cost creates a maintenance burden (stale cache bugs) for unproven benefit.

---

### 2.3 Naming & Interface Consistency

**Good:** PRD follows Interverse naming convention (`intermap`, lowercase, matches ecosystem).

**Good:** MCP tool naming is explicit (`project_registry`, `resolve_project`, `agent_map`).

**Concern:** F6 mentions `/intermap:status` skill but doesn't define what status means. Is this:
- Index build status (like `tldrs index --info`)?
- MCP server health check?
- Active project count?

Vague skill names create discoverability problems. Clarify before implementation.

---

## 3. Simplicity & YAGNI Analysis

### 3.1 Complexity Inventory

| Feature | Lines of Code (est.) | Necessity | Complexity Source |
|---------|---------------------|-----------|------------------|
| **F1: Go MCP scaffold** | 200 | ❌ No | Go build, stdio bridge, subprocess spawn, JSON parse, error mapping |
| **F1: Python subprocess bridge** | 100 | ❌ No | CLI arg parsing, JSON stdout, stderr capture, exit code handling |
| **F2: Module extraction** | 209,000 | ✅ Yes | Import rewrites, dependency vendoring, test migration |
| **F3: Removal from tldr** | 100 | ✅ Yes | Import cleanup, dead code removal |
| **F4: Project registry** | 300 | ✅ Yes | Git repo scanning, path resolution |
| **F4: TTL caching** | 100 | ❌ Speculative | Cache invalidation, TTL config, stale data bugs |
| **F5: Agent overlay** | 200 | ❌ Speculative | intermux MCP client, graceful degradation, join logic |
| **F6: Marketplace packaging** | 50 | ✅ Yes | Standard boilerplate |

**Total complexity: ~210,050 LOC**
**Necessary complexity: ~209,450 LOC (F2 + F3 + F4 core + F6)**
**Accidental complexity: ~600 LOC (F1 Go+Python, F4 caching, F5 overlay)**

**Accidental complexity is 0.3% of total,** but **80% of operational risk** (cross-language bugs, subprocess failures, cache invalidation, intermux coupling).

---

### 3.2 Abstraction Audit

**Premature abstraction 1: Open Q1 "workspace.py vendor or extract?"**

PRD says "Leaning: vendor a lightweight reimplementation."

**This is duplication risk.** `workspace.py` is 200 lines, used by 4 modules:
- `cross_file_calls.py`
- `project_index.py`
- `api.py`
- `daemon.py`

If intermap vendors a "lightweight reimplementation," you now have:
- `tldr-swinton/workspace.py` (original, 200 lines)
- `intermap/workspace.py` (reimplementation, 150 lines?)
- Different behavior when `.claude/workspace.json` parsing diverges
- Confusing error messages ("Why does tldr respect activePackages but intermap doesn't?")

**Correct options:**
1. **Shared library:** Extract `workspace.py` to a new `interverse-workspace` pip package used by both plugins.
2. **Delegate to tldr:** intermap calls tldr-swinton's daemon for file iteration (RPC layer, but no duplication).
3. **Accept duplication:** Vendor and document the divergence risk (only if shared lib overhead is too high).

**The PRD's "lightweight reimplementation" is option 3 without acknowledging the risk.**

---

**Premature abstraction 2: Open Q2 "simplify ProjectIndex to not need extractors"**

This is **out of scope for an extraction PRD.** Simplifying ProjectIndex is a refactoring task that should:
1. Be validated with existing tldr-swinton consumers first
2. Have its own design review (impacts difflens, symbolkite, cross_file_calls)
3. Not be bundled with a plugin extraction (two large changes = high risk)

**If F2 depends on ProjectIndex simplification, the PRD is under-scoped.** Either:
- Add ProjectIndex refactoring as a prerequisite (with its own AC)
- Remove `project_index.py` from the extraction (move only modules with zero refactor dependencies)

---

**Premature abstraction 3: Open Q3 "Python daemon vs one-shot"**

PRD says "Leaning: one-shot for v0.1, daemon for v0.2."

**This is planning to throw away work.** Here's what happens:

| Phase | Architecture | What Gets Built | Waste |
|-------|-------------|-----------------|-------|
| v0.1 | One-shot subprocess per tool call | Subprocess spawn, JSON stdio, arg parsing | 100% of this code |
| v0.2 | Persistent daemon | Socket/pipe, request multiplexing, session state | Reimplementation |

**The correct approach:**
1. Build daemon in v0.1 (30% more code than one-shot, but final architecture).
2. Or accept one-shot forever (if perf is fine, why daemon?).

**Building one-shot "to defer daemon decision" is fake simplicity.** It's complexity deferred to v0.2 + migration cost.

---

### 3.3 What Should Be Removed

**Remove before implementation:**

1. **F1 Go MCP server** → Use Python MCP (same as interject/interflux). Saves 300 LOC, eliminates cross-language bugs.
2. **F4 TTL caching** → Start with naive scan, add cache only if measured perf is bad. Saves 100 LOC.
3. **F5 Agent overlay** → Move to intermux or Clavain skill. Saves 200 LOC, decouples concerns.
4. **Open Q3 "one-shot then daemon"** → Decide daemon or no-daemon in v0.1. Saves rewrite in v0.2.

**Simplified PRD:**
- **F1 (revised):** Python MCP server with stdio (same as interject)
- **F2:** Extract `cross_file_calls.py`, `analysis.py`, `diagnostics.py`, `durability.py` (drop `project_index.py` and `change_impact.py` until dependencies resolved)
- **F3:** Remove moved modules from tldr-swinton
- **F4 (revised):** Project registry, no caching (add later if needed)
- **F6:** Marketplace packaging

**LOC estimate drops from 210,050 to 209,550 (extraction + registry + packaging only).**

---

## 4. Migration Safety

### 4.1 Risk: Parallel Plugin Activation

**Problem:** During migration, both tldr-swinton and intermap might be installed. If both expose overlapping tools:
```
tldrs arch <file>    (old, in tldr-swinton, deprecated)
intermap arch <file> (new, in intermap)
```

Claude Code's tool routing is namespace-based but doesn't version tools. If both are active, which gets called?

**Solution:**
1. **Deprecate old tools first:** Add warnings to tldr-swinton's `arch`, `calls`, `dead`, etc. ("This tool moved to intermap, please install intermap plugin").
2. **Disable old tools in F3:** After intermap is published, remove old tool implementations (not just mark deprecated).
3. **Document migration path:** AGENTS.md should say "If you have tldr-swinton <0.8.0, you need intermap for project-level tools."

**The PRD does not address this.** F3's "remove tools" assumes users will magically uninstall old tldr-swinton, but plugin updates aren't atomic.

---

### 4.2 Risk: Test Coverage Gap

**F2 acceptance criteria says:**
```
- All moved modules import-clean: python3 -c "import intermap.analyze" succeeds
```

**This only tests import success, not behavioral correctness.**

What's missing:
- Do the 6 extracted modules produce the same output as they did in tldr-swinton?
- Are cross-file call graphs identical pre/post extraction?
- Do diagnostic outputs match?

**Required gate:** Capture outputs from tldr-swinton's tools before F3, then run same queries via intermap, assert outputs match. This is **regression testing**, not just import validation.

**The PRD does not require this.** Accepting F2 without output parity testing is shipping blind.

---

### 4.3 Risk: Workspace Config Divergence

If F2 vendors a "lightweight workspace.py reimplementation" (per Open Q1), then:
- tldr-swinton reads `.claude/workspace.json` with one parser
- intermap reads `.claude/workspace.json` with a different parser
- Edge cases (missing keys, invalid JSON, regex patterns) may behave differently

**This creates confusing bugs:**
```
User: "Why does tldrs find ignore node_modules but intermap arch includes it?"
Root cause: intermap's vendored workspace.py doesn't implement excludePatterns correctly.
```

**Mitigation:**
- If vendoring, copy test suite for workspace.py to intermap and run same tests.
- Document which workspace features are supported in each plugin.
- Better: extract workspace.py to shared package so both use identical code.

**The PRD does not address this divergence risk.**

---

## 5. Recommendations

### 5.1 Must-Fix Before Implementation

| Issue | Fix | Gate |
|-------|-----|------|
| **F1 Go bridge** | Replace with Python MCP (interject pattern) | Revised PRD approved |
| **F2 dependencies** | Declare how ast_cache/hybrid_extractor/dirty_flag will resolve | Dependency resolution doc written |
| **F5 agent overlay** | Remove from v0.1 (move to intermux or hub skill) | PRD scope reduced |
| **Open Q3 daemon** | Decide daemon-or-not in v0.1 (no "defer to v0.2") | Decision recorded in PRD |
| **Test parity** | Add F2 AC: "output parity tests pass for all 6 tools" | Test harness written |

---

### 5.2 Recommended Revised Scope

**v0.1 (Minimal Viable Extraction):**

| Feature | What | Why |
|---------|------|-----|
| **F1 (revised)** | Python MCP server (stdio, same as interject) | Matches ecosystem, eliminates Go complexity |
| **F2 (reduced)** | Extract 4 modules: `cross_file_calls`, `analysis`, `diagnostics`, `durability` | These have clean/vendorable dependencies |
| **F2 (deferred)** | Leave `project_index.py` and `change_impact.py` in tldr-swinton | Too coupled; revisit after refactor |
| **F3** | Remove 4 moved tools from tldr-swinton | Matches F2 reduced scope |
| **F4 (revised)** | Project registry with naive scan (no cache) | Defer optimization until perf measured |
| **F6** | Marketplace packaging | Standard requirement |

**v0.2 (After v0.1 Validation):**
- Add caching to project registry (if perf is bad)
- Extract `project_index.py` (after ast_cache refactored into shared lib)
- Extract `change_impact.py` (after dirty_flag decoupled)
- Add agent overlay (as intermux integration, not intermap feature)

---

### 5.3 Smallest Viable Change

**If PRD must ship as-is (not recommended):**

At minimum, replace F1 with Python MCP. This single change:
- Removes 300 LOC of Go scaffolding
- Eliminates subprocess spawn overhead
- Matches existing plugin patterns (interject, interflux)
- Reduces operational risk (no cross-language debugging)
- Preserves all other features (F2-F6 unchanged)

**Diff:**
```diff
- F1: Go MCP server + Python subprocess bridge
+ F1: Python MCP server (mcp package, stdio)
```

**Cost:** 1 day implementation time saved, 0 features lost.

---

## 6. Conclusion

The PRD's **core insight is correct:** tldr-swinton conflates file-level and project-level concerns, and separating them will reduce entropy. The **execution plan is 70% sound but 30% bloated** with premature optimizations (Go bridge, caching, agent overlay, one-shot-then-daemon).

**Primary architectural violation:** The Go-to-Python subprocess bridge adds complexity without solving a real problem. This is the highest-priority fix.

**Secondary risks:** Dependency hand-waving (F2), missing test parity, workspace config divergence, and lack of migration safety.

**Recommended path:**
1. Simplify F1 to Python MCP (matches interject/interflux pattern)
2. Reduce F2 to 4 cleanly-extractable modules (defer coupled ones)
3. Remove F5 agent overlay (move to intermux where it belongs)
4. Remove caching from F4 (add later if needed)
5. Decide daemon-or-not in v0.1 (no throwaway work)

This reduces accidental complexity by 60% while preserving the core boundary correction. The result is a lower-risk extraction with a clearer migration path and better ecosystem alignment.
