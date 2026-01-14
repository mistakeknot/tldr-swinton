# Context Optimization Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `[none] (Task reference)` — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Align the context-optimization roadmap with the current repo and implement Phase 0 fixes with unified symbol identity, traversal, formatting, and consistent ignore handling (.tldrsignore).

**Architecture:** Introduce a unified SymbolId and workspace file iterator, migrate context/impact/semantic paths to use them, and standardize output formatting across CLI and MCP. Replace legacy .tldrignore usage with .tldrsignore and correct doc references.

**Tech Stack:** Python 3, tree-sitter, FAISS, CLI/MCP tooling.

### Task 1: Update roadmap documentation (correct paths, statuses, .tldrsignore)

**Files:**
- Modify: `docs/plans/context-optimization-roadmap.md`

**Step 1: Write the failing test**

Not applicable (doc-only change).

**Step 2: Run test to verify it fails**

Not applicable.

**Step 3: Write minimal implementation**

Update file references (e.g., call graph and ignore module), correct status notes vs current repo, and fix .tldrsignore naming.

**Step 4: Run test to verify it passes**

Not applicable.

**Step 5: Commit**

```bash
git add docs/plans/context-optimization-roadmap.md
git commit -m "docs: align context optimization roadmap with repo"
```

### Task 2: Standardize ignore handling to .tldrsignore (rename module + update imports)

**Files:**
- Move: `src/tldr_swinton/tldrignore.py` -> `src/tldr_swinton/tldrsignore.py`
- Modify: `src/tldr_swinton/cross_file_calls.py`
- Modify: `src/tldr_swinton/index.py`
- Modify: `src/tldr_swinton/api.py`
- Modify: any other references to .tldrignore

**Step 1: Write the failing test**

Not applicable (refactor/integration change).

**Step 2: Run test to verify it fails**

Not applicable.

**Step 3: Write minimal implementation**

Rename module, update imports, and ensure on-disk filename expectations use `.tldrsignore` consistently.

**Step 4: Run test to verify it passes**

Smoke check by running a simple import:
```bash
python -c "from tldr_swinton import tldrsignore; print(tldrsignore.DEFAULT_TEMPLATE[:20])"
```
Expected: prints a prefix of the template string.

**Step 5: Commit**

```bash
git add src/tldr_swinton/tldrsignore.py src/tldr_swinton/cross_file_calls.py src/tldr_swinton/index.py src/tldr_swinton/api.py
git commit -m "refactor: standardize .tldrsignore handling"
```

### Task 3: Unify workspace file traversal across context/index/structure

**Files:**
- Modify: `src/tldr_swinton/workspace.py`
- Modify: `src/tldr_swinton/api.py`
- Modify: `src/tldr_swinton/index.py`
- Modify: `src/tldr_swinton/cross_file_calls.py` (if needed)

**Step 1: Write the failing test**

Not applicable.

**Step 2: Run test to verify it fails**

Not applicable.

**Step 3: Write minimal implementation**

Add a shared iterator that applies .tldrsignore + workspace config; use it in context and code structure to remove ad-hoc rglob and SKIP_DIRS.

**Step 4: Run test to verify it passes**

Manual smoke check (no automated tests):
```bash
python -c "from tldr_swinton.workspace import iter_workspace_files; print(len(list(iter_workspace_files('.', {'.py'}))))"
```
Expected: prints a non-zero count for this repo.

**Step 5: Commit**

```bash
git add src/tldr_swinton/workspace.py src/tldr_swinton/api.py src/tldr_swinton/index.py src/tldr_swinton/cross_file_calls.py
git commit -m "refactor: unify workspace file traversal"
```

### Task 4: SymbolId unification in relevant context + impact analysis

**Files:**
- Modify: `src/tldr_swinton/api.py`
- Modify: `src/tldr_swinton/analysis.py`

**Step 1: Write the failing test**

Not applicable.

**Step 2: Run test to verify it fails**

Not applicable.

**Step 3: Write minimal implementation**

Use file-qualified SymbolId for adjacency/visited/queue in `get_relevant_context`, fix ambiguity handling, and update impact analysis to use file-qualified nodes (with disambiguation on bare names).

**Step 4: Run test to verify it passes**

Manual smoke check (no automated tests):
```bash
python -c "from tldr_swinton.api import get_relevant_context; print(get_relevant_context('.', 'get_relevant_context', depth=1).functions[:1])"
```
Expected: prints a FunctionContext with file-qualified name.

**Step 5: Commit**

```bash
git add src/tldr_swinton/api.py src/tldr_swinton/analysis.py
git commit -m "refactor: use SymbolId for context traversal"
```

### Task 5: Output formatting fixes (indent depth, docstrings default, ultracompact)

**Files:**
- Modify: `src/tldr_swinton/api.py`
- Modify: `src/tldr_swinton/cli.py`
- Create: `src/tldr_swinton/output_formats.py` (if needed)

**Step 1: Write the failing test**

Not applicable.

**Step 2: Run test to verify it fails**

Not applicable.

**Step 3: Write minimal implementation**

Fix indentation in `to_llm_string()` to use BFS depth; default `include_docstrings=False`; add `--with-docs` and `--format ultracompact` support.

**Step 4: Run test to verify it passes**

Manual smoke check:
```bash
python -c "from tldr_swinton.api import get_relevant_context; print(get_relevant_context('.', 'get_relevant_context', depth=1).to_llm_string().splitlines()[0])"
```
Expected: a header line without errors.

**Step 5: Commit**

```bash
git add src/tldr_swinton/api.py src/tldr_swinton/cli.py src/tldr_swinton/output_formats.py
git commit -m "feat: ultracompact context + docstring defaults"
```

### Task 6: Unify semantic search + MCP formatting, wire tldr-bench variants

**Files:**
- Modify: `src/tldr_swinton/daemon.py`
- Modify: `src/tldr_swinton/mcp_server.py`
- Modify: `src/tldr_swinton/cli.py`
- Modify: `tldr-bench/tldr_bench/variants/difflens.py`
- Modify: `tldr-bench/tldr_bench/variants/symbolkite.py`
- Modify: `tldr-bench/tldr_bench/variants/coveragelens.py`

**Step 1: Write the failing test**

Not applicable.

**Step 2: Run test to verify it fails**

Not applicable.

**Step 3: Write minimal implementation**

Route daemon semantic/index to `index.py` backend; use shared formatter in MCP `context`; wire tldr-bench variants to call API stubs or context functions.

**Step 4: Run test to verify it passes**

Manual smoke check:
```bash
python -c "from tldr_swinton.index import index_project; print('ok')"
```
Expected: prints ok (index may still require dependencies).

**Step 5: Commit**

```bash
git add src/tldr_swinton/daemon.py src/tldr_swinton/mcp_server.py src/tldr_swinton/cli.py tldr-bench/tldr_bench/variants/difflens.py tldr-bench/tldr_bench/variants/symbolkite.py tldr-bench/tldr_bench/variants/coveragelens.py
git commit -m "feat: unify semantic search + wire bench variants"
```
