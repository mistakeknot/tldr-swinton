# Intermap PRD — Correctness Review

**Reviewer:** Julik (Flux-drive Correctness Reviewer)
**Date:** 2026-02-16
**PRD:** `/root/projects/Interverse/docs/prds/2026-02-16-intermap-extraction.md`
**Context:** Moving 6 Python modules (~209 KB) from tldr-swinton to intermap, breaking import chains, maintaining two MCP servers

---

## Executive Summary

This extraction plan proposes splitting tldr-swinton's project-level analysis modules into a new intermap plugin. The primary correctness risks are:

1. **Circular import hazard** — `project_index.py` depends on 4 internal modules; vendoring creates a maintenance fork
2. **Missing subprocess atomicity** — Go→Python bridge lacks cancellation discipline and orphan cleanup
3. **Call graph consistency gap** — no validation that moved modules produce identical results post-extraction
4. **Daemon protocol coupling** — `change_impact.py` imports `dirty_flag` which imports the MCP daemon; breaks if daemon unavailable
5. **Undefined failure modes** — PRD does not specify recovery behavior when Python subprocess fails mid-operation

**Severity ranking:** Medium-high. The plan is structurally sound but missing concurrency guardrails and validation steps.

---

## Invariant Statement

### What Must Remain True

1. **Import isolation:** intermap's Python package must run with zero tldr-swinton imports after extraction
2. **Tool parity:** The 6 moved MCP tools (`arch`, `calls`, `dead`, `impact`, `change_impact`, `diagnostics`) must produce identical output before and after migration
3. **Subprocess lifecycle:** Every Python subprocess spawned by Go must be cancelled/killed when the parent MCP request is cancelled
4. **Error propagation:** Non-zero Python exit codes must propagate as MCP tool errors with full stderr context
5. **Dependency completeness:** Moved modules must carry all transitive dependencies or vendor minimal stubs
6. **tldr-swinton stability:** The remaining tldr-swinton installation must pass all existing tests after module removal

---

## Data Integrity Risks

### DI-1: Circular Import Hazard (High)

**Location:** F2 acceptance criterion for `project_index.py`

**The problem:**
```python
# project_index.py imports:
from .ast_cache import ASTCache                    # 57 lines, imports hybrid_extractor
from .ast_extractor import FunctionInfo            # 646 lines, no internal deps (safe)
from .cross_file_calls import build_project_call_graph  # 119 KB, imports workspace
from .hybrid_extractor import HybridExtractor      # 1280 lines, imports ast_extractor + signature_extractor
from .workspace import iter_workspace_files        # 181 lines, no internal deps (safe)
```

**The failure narrative:**
1. Intermap vendors `project_index.py` + `workspace.py` + `ast_extractor.py` as "minimal stubs"
2. `cross_file_calls.py` (119 KB) is moved wholesale
3. `cross_file_calls` imports `workspace.WorkspaceConfig` and `load_workspace_config`
4. Now intermap has two copies of `workspace.py`: vendored stub and the full one imported by `cross_file_calls`
5. Type checking passes but runtime behavior diverges because `WorkspaceConfig` from stub ≠ `WorkspaceConfig` from full module
6. Call graphs become incomplete when workspace filtering logic differs between stubs

**Consequences:**
- `arch`, `calls`, `dead`, `impact` tools silently return incorrect results
- No error is raised — the tools "work" but with wrong data
- Regression discovered only when user notices missing edges in call graph

**Corrective action:**
1. **Do NOT vendor `workspace.py`** — move it wholesale to intermap or extract to a shared `intercommon` package
2. Document the full dependency closure for each moved module before extraction begins
3. Add a pre-commit hook that runs `python -c "import intermap.analyze"` and validates zero tldr-swinton imports via `sys.modules` inspection
4. Create a migration checklist:
   ```
   [ ] List all direct imports for each moved module
   [ ] List all transitive imports (imports of imports)
   [ ] Identify shared modules (workspace, ast_extractor, hybrid_extractor)
   [ ] Decision: Move shared modules or vendor minimal interface?
   [ ] If vendoring: freeze the interface contract (dataclass shapes, function signatures)
   [ ] Post-extraction: run `grep -r "from tldr_swinton" intermap/` — must be empty
   ```

**Recommended dependency strategy:**
- **Move wholesale:** `workspace.py` (181 lines, no internal deps, used by 4 moved modules)
- **Move wholesale:** `cross_file_calls.py` (119 KB, already planned in F2)
- **Vendor minimal:** `ast_extractor.FunctionInfo` dataclass only (freeze shape, import from tldr-swinton at runtime if installed, else use vendored stub)
- **Replace:** `ast_cache.ASTCache` — reimplement as file-based cache using hashlib + JSON, no daemon dependency
- **Replace:** `hybrid_extractor.HybridExtractor` — intermap only needs call graph extraction, not full AST analysis; simplify to tree-sitter-only call site parser

---

### DI-2: Daemon Protocol Coupling (Medium)

**Location:** F2 — `change_impact.py` (12 KB) imports `dirty_flag.py` (dirty_flag imports daemon state)

**The problem:**
```python
# change_impact.py:15
from .dirty_flag import get_dirty_files

# dirty_flag.py reads .tldrs/dirty_flag.json written by daemon
# If daemon is not running, get_dirty_files() returns empty list (silent degradation)
```

**Failure narrative:**
1. User calls intermap's `change_impact` MCP tool
2. Tool calls `get_dirty_files()` to find modified files
3. Daemon is not running (user is not using tldr-swinton, only intermap)
4. Returns `[]`, tool reports "No changed files detected"
5. User expects impact analysis for recent edits; gets empty result with no warning

**Corrective action:**
1. **Option A (recommended):** Remove `dirty_flag` dependency from `change_impact.py`
   - Fallback to git diff for file discovery (`git diff --name-only HEAD`)
   - Make daemon-based tracking optional/future work
2. **Option B:** Vendor `dirty_flag.py` and implement standalone file-watcher in Go
   - Requires inotify/fsnotify integration in intermap's Go binary
   - Higher complexity, deferred to v0.2
3. Add explicit warning in `change_impact` tool description: "Requires git repository or explicit `--files` argument"

---

### DI-3: Call Graph Consistency Gap (High)

**Location:** No validation step in PRD for correctness of moved modules

**Invariant violation risk:**
After extraction, `intermap`'s `calls` tool may produce different edges than pre-extraction `tldr-swinton`'s `calls` tool due to:
- Missing transitive dependencies
- Vendored stubs with divergent behavior
- Tree-sitter parser version drift (if intermap pins different versions)

**The test that should exist but doesn't:**
```python
# Pre-extraction: capture baseline
tldrs_result = subprocess.run(["tldrs", "calls", "--project", ".", "--format", "json"])
baseline = json.loads(tldrs_result.stdout)

# Post-extraction: compare intermap output
intermap_result = subprocess.run(["intermap", "calls", "--project", ".", "--format", "json"])
actual = json.loads(intermap_result.stdout)

# Verify edge parity
assert set(baseline["edges"]) == set(actual["edges"]), "Call graph edges diverged after extraction"
```

**Corrective action:**
1. Add F7 to PRD: **Equivalence Testing**
   ```
   Acceptance criteria:
   - [ ] Capture baseline outputs for all 6 moved tools on 3 test repos (Python, TypeScript, Go)
   - [ ] After extraction, re-run tools via intermap; outputs must match byte-for-byte (ignoring timestamps)
   - [ ] Store baselines in `intermap/tests/fixtures/migration_baselines/`
   - [ ] Add pytest suite: `tests/test_migration_parity.py`
   - [ ] CI gate: migration parity tests must pass before F6 (marketplace publish)
   ```

---

## Concurrency Risks

### C-1: Missing Subprocess Cancellation (High)

**Location:** F1 — Go MCP server invokes `python3 -m intermap.analyze --command=X` via subprocess

**The problem:**
```go
// Hypothetical implementation (not in PRD)
func (s *Server) handleAnalyzeRequest(ctx context.Context, req AnalyzeRequest) ([]byte, error) {
    cmd := exec.Command("python3", "-m", "intermap.analyze", "--command", req.Command, "--project", req.Project)
    output, err := cmd.CombinedOutput()  // BLOCKS until Python exits
    if err != nil {
        return nil, fmt.Errorf("python error: %w", err)
    }
    return output, nil
}
```

**Race narrative:**
1. Claude Code calls intermap's `arch` MCP tool on a 10 GB monorepo
2. Python subprocess starts building call graph (30+ second operation)
3. User cancels the Claude request (Ctrl+C or timeout)
4. Go MCP server receives cancellation via `ctx.Done()`
5. Python subprocess keeps running (no signal sent)
6. After 30 seconds, Python writes output to stdout
7. Go binary has already exited; stdout is closed
8. Python receives SIGPIPE, crashes with BrokenPipeError
9. Orphaned Python process leaks until manual kill

**Consequences:**
- Resource leak: Python processes accumulate after repeated cancellations
- Disk churn: Partial call graph indexes pollute cache dirs
- User confusion: "Why is Python still using CPU after I cancelled?"

**Corrective action:**
1. Use `exec.CommandContext(ctx, ...)` instead of `exec.Command`
2. Propagate cancellation signal to subprocess:
   ```go
   func (s *Server) handleAnalyzeRequest(ctx context.Context, req AnalyzeRequest) ([]byte, error) {
       cmd := exec.CommandContext(ctx, "python3", "-m", "intermap.analyze", "--command", req.Command, "--project", req.Project)

       var stdout, stderr bytes.Buffer
       cmd.Stdout = &stdout
       cmd.Stderr = &stderr

       err := cmd.Run()
       if ctx.Err() != nil {
           return nil, fmt.Errorf("request cancelled: %w", ctx.Err())
       }
       if err != nil {
           return nil, fmt.Errorf("python failed: %w\nstderr: %s", err, stderr.String())
       }
       return stdout.Bytes(), nil
   }
   ```
3. Add Python signal handler for graceful shutdown:
   ```python
   # intermap/analyze.py
   import signal
   import sys

   def signal_handler(sig, frame):
       sys.stderr.write("Received termination signal, cleaning up...\n")
       sys.exit(130)  # 128 + SIGINT

   signal.signal(signal.SIGTERM, signal_handler)
   signal.signal(signal.SIGINT, signal_handler)
   ```
4. Document subprocess lifecycle in F1 acceptance criteria

---

### C-2: No Timeout Strategy (Medium)

**Location:** F1 — Python subprocess bridge has no timeout bounds

**Failure mode:**
- User runs `impact` analysis on pathological call graph with 100K+ functions
- Python process runs for 10+ minutes building reverse graph
- MCP client times out (default 60s)
- Go server still blocked on `cmd.CombinedOutput()`
- No way to cancel or recover

**Corrective action:**
1. Add per-tool timeout configuration:
   ```go
   var toolTimeouts = map[string]time.Duration{
       "arch":          120 * time.Second,
       "calls":         180 * time.Second,
       "dead":          90 * time.Second,
       "impact":        60 * time.Second,
       "change_impact": 45 * time.Second,
       "diagnostics":   30 * time.Second,
   }
   ```
2. Wrap each call with timeout context:
   ```go
   timeout := toolTimeouts[req.Command]
   ctx, cancel := context.WithTimeout(parentCtx, timeout)
   defer cancel()

   cmd := exec.CommandContext(ctx, "python3", "-m", "intermap.analyze", ...)
   ```
3. Return actionable error when timeout is hit:
   ```
   "Analysis timed out after 120s. Try narrowing scope with --active-packages in .claude/workspace.json"
   ```

---

### C-3: Concurrent Call Graph Builds (Low)

**Location:** F4 — Project registry caches results with 5 min TTL

**Race scenario:**
1. Two MCP requests arrive simultaneously for the same project
2. Both spawn `build_project_call_graph()` in separate Python processes
3. Both write to same temp file: `.tldrs/call_graph_cache.json`
4. Writes interleave, JSON becomes malformed
5. Next request fails to parse cache, rebuilds from scratch

**Why this is low severity:**
- Call graph building is read-only (no data corruption)
- Worst case is wasted CPU, not incorrect results
- Cache writes are atomic (write temp, rename) in most implementations

**Mitigations (optional):**
1. Use process-scoped temp files: `.tldrs/call_graph_cache.$PID.json`
2. Add file locking for cache writes (flock on Linux, LockFileEx on Windows)
3. Detect stale cache via mtime comparison before reading

---

## Missing Guardrails

### MG-1: No Rollback Plan

**If extraction breaks tldr-swinton:**
- Users who update tldr-swinton to version N+1 (with modules removed) but don't install intermap are left with broken `arch`, `calls`, `dead`, `impact`, `change_impact`, `diagnostics` commands
- No fallback, no migration script, no version compatibility matrix

**Required additions to PRD:**
1. **Dual-plugin transition period (2 releases)**
   - v0.7.13: Add deprecation warnings to 6 tools in tldr-swinton: "This tool will move to intermap in v0.8.0. Install intermap now for seamless migration."
   - v0.8.0: Remove tools from tldr-swinton, marketplace updated with intermap dependency
   - v0.8.1: Verify no user complaints about missing tools
2. **Marketplace dependency declaration**
   ```json
   // tldr-swinton/plugin.json v0.8.0+
   {
     "suggests": ["intermap"],
     "migration_notes": "The arch/calls/dead/impact/change_impact/diagnostics commands moved to intermap. Install it via: claude plugins install intermap"
   }
   ```
3. **Stub commands in tldr-swinton post-removal**
   ```bash
   # tldrs arch
   Error: The 'arch' command moved to the intermap plugin.
   Install it with: claude plugins install intermap
   Then use: /intermap:arch
   ```

---

### MG-2: No Integration Test for Go↔Python Bridge

**F1 says "Python subprocess bridge" but doesn't specify test coverage**

**What should be tested:**
```python
# tests/test_subprocess_bridge.py

def test_python_success():
    """Normal case: Python returns JSON, exit 0"""
    result = call_mcp_tool("arch", project="./fixtures/tiny_project")
    assert result["layer_count"] > 0

def test_python_stderr_captured():
    """Error case: Python prints to stderr, exit 1"""
    result = call_mcp_tool("impact", project="/nonexistent")
    assert "error" in result
    assert "FileNotFoundError" in result["error"]

def test_python_timeout():
    """Timeout case: Python runs longer than deadline"""
    with pytest.raises(TimeoutError):
        call_mcp_tool("calls", project="./fixtures/huge_project", timeout=1)

def test_python_cancelled():
    """Cancellation case: Go context cancelled mid-execution"""
    ctx, cancel = context.WithCancel(context.Background())
    go func() { time.Sleep(100 * time.Millisecond); cancel() }()
    _, err := handleAnalyzeRequest(ctx, AnalyzeRequest{...})
    assert.ErrorIs(err, context.Canceled)
```

**Add to F1 acceptance criteria:**
```
- [ ] Test suite covers: success, stderr capture, timeout, cancellation, malformed JSON
- [ ] All tests pass on Linux, macOS, Windows
```

---

### MG-3: Undefined Python Dependency Management

**F2 says "move 6 modules" but doesn't say how Python dependencies are declared**

**Questions the PRD must answer:**
1. Does intermap have its own `pyproject.toml`? Or does it call `python3 -m tldr_swinton.modules.core.analysis`?
2. If separate package: what are the dependencies? (tree-sitter, tree-sitter-python, tree-sitter-typescript, etc.)
3. How does the Go binary ensure Python dependencies are installed before calling subprocess?
4. What happens if user's Python is 3.8 but intermap requires 3.10+?

**Required additions:**
```toml
# intermap/python/pyproject.toml
[project]
name = "intermap-analyze"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "tree-sitter>=0.21.0",
    "tree-sitter-python>=0.21.0",
    "tree-sitter-typescript>=0.21.0",
    "tree-sitter-go>=0.21.0",
    "tree-sitter-rust>=0.21.0",
]
```

```bash
# bin/launch-mcp.sh (add Python venv check)
PYTHON_VENV="$PLUGIN_DIR/python/.venv"
if [ ! -d "$PYTHON_VENV" ]; then
    echo "Installing Python dependencies..." >&2
    cd "$PLUGIN_DIR/python"
    python3 -m venv .venv
    .venv/bin/pip install -e .
fi
export INTERMAP_PYTHON="$PYTHON_VENV/bin/python3"
exec "$PLUGIN_DIR/bin/intermap-mcp"
```

---

## Recommended Acceptance Criteria Additions

### F1 Enhancement: Subprocess Bridge
```diff
 - [ ] Python subprocess bridge: Go calls `python3 -m intermap.analyze --command=X --project=Y` and parses JSON stdout
 - [ ] Error handling: Python stderr captured, non-zero exit → MCP tool error
+- [ ] Cancellation: Uses exec.CommandContext, propagates ctx.Done() to subprocess SIGTERM
+- [ ] Timeout: Per-tool timeout bounds (arch: 120s, calls: 180s, impact: 60s, etc.)
+- [ ] Orphan cleanup: No subprocess leaks after request cancellation
+- [ ] Integration tests: success, stderr, timeout, cancellation, malformed JSON
```

### F2 Enhancement: Import Isolation
```diff
 - [ ] All moved modules import-clean: `python3 -c "import intermap.analyze"` succeeds without tldr-swinton installed
+- [ ] Dependency closure documented: List all direct + transitive imports for each moved module
+- [ ] Shared modules strategy: workspace.py moved wholesale (not vendored stub)
+- [ ] Pre-commit hook: Validates zero tldr-swinton imports via sys.modules inspection
+- [ ] Equivalence baseline: Capture pre-extraction outputs for 6 tools on 3 test repos
```

### F7 (NEW): Migration Validation
```
**What:** Verify that moved tools produce identical results before and after extraction.
**Acceptance criteria:**
- [ ] Baseline outputs captured for all 6 tools (arch, calls, dead, impact, change_impact, diagnostics) on 3 repos
- [ ] Post-extraction: intermap outputs match tldr-swinton baselines byte-for-byte (ignoring timestamps/paths)
- [ ] Pytest suite: tests/test_migration_parity.py with frozen fixtures
- [ ] CI gate: Parity tests must pass before F6 (marketplace publish)
- [ ] Rollback plan documented: What to do if post-extraction tests fail
```

---

## Open Questions (Require Decisions Before Implementation)

### OQ-1: Workspace.py Shared Dependency
**Current plan:** "Vendor a minimal copy into intermap, or extract to a shared package"

**Decision required:**
- **Option A:** Move `workspace.py` wholesale to intermap (breaks tldr-swinton's dependency on it → must also vendor/stub in tldr-swinton)
- **Option B:** Extract to `intercommon` shared package, both plugins depend on it
- **Option C:** Duplicate `workspace.py` in both plugins (maintenance burden)

**Recommendation:** Option B (shared package) to avoid circular vendoring and maintenance drift.

---

### OQ-2: ProjectIndex Simplification Strategy
**Current plan:** "Simplify ProjectIndex to not need ast_cache/ast_extractor/hybrid_extractor"

**Decision required:**
- What subset of ProjectIndex functionality does intermap actually need?
- Can we replace `HybridExtractor` with a tree-sitter-only call site parser?
- Can we replace `ASTCache` with simple file mtime caching?

**Recommendation:** Prototype a minimal `InterMapIndex` that only builds call graphs (no full symbol extraction) and measure if analysis quality degrades.

---

### OQ-3: Python Daemon vs One-Shot
**Current plan:** "One-shot for v0.1, daemon for v0.2 if performance needs it"

**Decision required:**
- What is the performance penalty for one-shot subprocess calls?
- Benchmark: Run `calls` tool 10 times on a 100-file project; measure total wall time
- If < 5s total, one-shot is fine. If > 10s, daemon is required for usability.

**Recommendation:** Add benchmark to F1 acceptance criteria; defer daemon to v0.2 only if benchmark shows >10s penalty.

---

## Severity Summary

| Risk ID | Severity | Impact | Likelihood | Mitigation Effort |
|---------|----------|--------|------------|-------------------|
| DI-1    | High     | Incorrect call graphs (silent data corruption) | High (vendoring without interface freeze) | Medium (doc dependency closure, move workspace.py) |
| DI-2    | Medium   | Empty results when daemon unavailable | Medium (if user doesn't run tldr-swinton daemon) | Low (fallback to git diff) |
| DI-3    | High     | Divergent outputs post-extraction | High (no validation planned) | Medium (add equivalence test suite) |
| C-1     | High     | Subprocess leaks after cancellation | High (every cancellation leaks a process) | Low (use exec.CommandContext) |
| C-2     | Medium   | Unbounded subprocess runtime | Medium (large repos trigger timeout) | Low (add per-tool timeout map) |
| C-3     | Low      | Concurrent cache writes (rare corruption) | Low (requires simultaneous requests) | Low (atomic writes already standard) |
| MG-1    | High     | Broken user workflows if partial migration | High (users update plugin without installing intermap) | Medium (2-release deprecation, stub commands) |
| MG-2    | Medium   | Untested subprocess failure modes | High (no tests = bugs in production) | Medium (write integration test suite) |
| MG-3    | Medium   | Python dependency mismatch | Medium (user's env lacks tree-sitter) | Low (venv setup in launch script) |

**Blocking risks (must address before F6 publish):**
1. DI-1 (circular import hazard)
2. DI-3 (no equivalence validation)
3. C-1 (subprocess cancellation)
4. MG-1 (no rollback plan)

---

## Recommended Implementation Order

To minimize correctness risk, execute features in this order:

1. **F2 (module extraction)** — but STOP before removing from tldr-swinton
2. **F7 (new: migration validation)** — capture baselines, write parity tests
3. **F1 (Go MCP scaffold)** — with subprocess cancellation + timeout from day 1
4. **Run F7 parity tests** — if they fail, fix vendoring/dependency issues before proceeding
5. **F3 (remove from tldr-swinton)** — only after F7 tests pass
6. **F4 + F5 (registry + agent overlay)** — these are additive, lower risk
7. **F6 (marketplace publish)** — final gate: all tests green, migration guide written

**Do NOT proceed to F3 (removal) until F7 (parity tests) pass.** Removing tools before validating equivalence creates a one-way door with no rollback.

---

## Final Recommendation

**The PRD is structurally sound but missing critical validation and concurrency guardrails.**

### Must-fix before implementation:
1. Add F7 (Migration Validation) with baseline capture + parity tests
2. Document full dependency closure for each moved module (avoid vendoring traps)
3. Add subprocess cancellation (exec.CommandContext) and timeout strategy to F1
4. Add 2-release deprecation plan to avoid breaking user workflows

### Nice-to-have (can defer):
- Concurrent cache write locking (C-3)
- Python daemon for performance (OQ-3, defer to v0.2)
- Agent overlay integration with intermux (F5, works standalone without)

### Approval gate:
Before merging this extraction, the following MUST be green:
- [ ] Parity tests pass on 3 representative repos (Python, TypeScript, Go)
- [ ] `python3 -c "import intermap.analyze"` runs with zero tldr-swinton imports
- [ ] Subprocess cancellation test passes (no orphaned processes)
- [ ] tldr-swinton test suite passes after module removal

**Risk level: Medium-high → Medium (after fixes applied)**

---

**Correctness verdict:** Proceed with caution. Add validation steps before removal. The architecture is clean, but the migration path needs guardrails.
