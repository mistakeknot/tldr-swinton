# Phase 0 Gaps Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-9jp` (Task reference)

**Goal:** Close Phase 0 roadmap gaps by fixing symbol identity, ignore traversal, real token budgeting, and semantic signature formatting.

**Architecture:** Normalize call-graph identities to canonical `rel_path:qualified_name` strings, route all traversal through `.tldrsignore`-aware helpers, and make budgets use tokenizer-backed counts. Keep changes incremental to existing APIs, and add focused tests per behavior.

**Tech Stack:** Python, pytest, tiktoken, tree-sitter (optional), tldr_swinton internal helpers (`workspace.iter_workspace_files`).

---

### Task 1: Canonical symbol IDs in call graph + analysis

**Files:**
- Modify: `src/tldr_swinton/cross_file_calls.py`
- Modify: `src/tldr_swinton/analysis.py`
- Modify: `src/tldr_swinton/api.py`
- Test: `tests/test_call_graph_symbol_ids.py` (new)

**Step 1: Write the failing test**

Create `tests/test_call_graph_symbol_ids.py`:

```python
from pathlib import Path

from tldr_swinton.analysis import impact_analysis
from tldr_swinton.cross_file_calls import build_project_call_graph


def test_call_graph_uses_qualified_method_names(tmp_path: Path) -> None:
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "mod.py").write_text(
        """
class A:
    def run(self):
        helper()

class B:
    def run(self):
        helper()

def helper():
    return 1
""".lstrip()
    )

    graph = build_project_call_graph(str(tmp_path), language="python")
    # Ensure both qualified method names appear in graph edges
    edge_names = {edge[1] for edge in graph.edges} | {edge[3] for edge in graph.edges}
    assert "A.run" in edge_names
    assert "B.run" in edge_names

    result = impact_analysis(graph, "A.run", target_file="pkg/mod.py")
    assert "pkg/mod.py:A.run" in result["targets"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_call_graph_symbol_ids.py::test_call_graph_uses_qualified_method_names -v`

Expected: FAIL (qualified names not present; impact_analysis can’t resolve `A.run`).

**Step 3: Implement minimal call graph qualification**

In `src/tldr_swinton/cross_file_calls.py`:
- Update Python call extraction to include class context:
  - Track current class when walking the AST.
  - Record function keys as `Class.method` for methods.
  - When encountering `self.method()` or `cls.method()`, map to `Class.method` using the current class.
- When collecting `defined_funcs`, include qualified method names and keep a map `{method_name -> Class.method}` for disambiguation within class scope.
- Update the module-level synthetic function name to include a stable symbol id like `<module>` for consistency.

In `src/tldr_swinton/analysis.py`:
- Treat `target_func` as fully-qualified name when provided.
- Build FunctionRef reprs using canonical `rel_path:qualified_name` (no more collisions on identical method names).

In `src/tldr_swinton/api.py`:
- Ensure adjacency resolution prefers fully-qualified names when present.
- When `entry_point` includes `Class.method`, resolve to symbol IDs matching the new qualified names.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_call_graph_symbol_ids.py::test_call_graph_uses_qualified_method_names -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/cross_file_calls.py src/tldr_swinton/analysis.py src/tldr_swinton/api.py tests/test_call_graph_symbol_ids.py
git commit -m "fix: qualify call graph symbol ids"
```

---

### Task 2: Enforce .tldrsignore in traversal (search + daemon)

**Files:**
- Modify: `src/tldr_swinton/api.py`
- Modify: `src/tldr_swinton/daemon.py`
- Test: `tests/test_search_respects_ignore.py` (new)

**Step 1: Write the failing test**

Create `tests/test_search_respects_ignore.py`:

```python
from pathlib import Path

from tldr_swinton.api import search


def test_search_respects_tldrsignore(tmp_path: Path) -> None:
    (tmp_path / ".tldrsignore").write_text("ignored/\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "skip.py").write_text("def skip():\n    pass\n")
    (tmp_path / "keep.py").write_text("def keep():\n    pass\n")

    results = search("def", tmp_path, extensions={".py"})
    files = {r["file"] for r in results}
    assert "keep.py" in files
    assert "ignored/skip.py" not in files
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_search_respects_ignore.py::test_search_respects_tldrsignore -v`

Expected: FAIL (search still uses rglob + SKIP_DIRS).

**Step 3: Implement ignore-aware traversal**

In `src/tldr_swinton/api.py`:
- Replace `root.rglob("*")` in `search()` with `iter_workspace_files`.
- Respect `extensions` and `max_files` inside the loop.
- Keep `max_results` and `context_lines` behavior unchanged.

In `src/tldr_swinton/daemon.py`:
- Replace `self.project.rglob("*.py")` in `_ensure_dedup_index_loaded()` with `iter_workspace_files(self.project, extensions={".py"})`.
- Preserve existing skip behavior for `.venv` / `__pycache__` (should be covered by ignore anyway).

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_search_respects_ignore.py::test_search_respects_tldrsignore -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/api.py src/tldr_swinton/daemon.py tests/test_search_respects_ignore.py
git commit -m "fix: respect .tldrsignore in traversal"
```

---

### Task 3: Real token budgeting using tiktoken

**Files:**
- Modify: `src/tldr_swinton/output_formats.py`
- Test: `tests/test_budget_tokens.py` (new)

**Step 1: Write the failing test**

Create `tests/test_budget_tokens.py`:

```python
from tldr_swinton.output_formats import _estimate_tokens, _apply_budget


def test_estimate_tokens_monotonic() -> None:
    short = _estimate_tokens("hello")
    long = _estimate_tokens("hello world " * 10)
    assert long > short


def test_apply_budget_stops_on_token_limit() -> None:
    lines = ["alpha " * 20, "beta " * 20]
    limited = _apply_budget(lines, budget_tokens=5)
    assert limited[-1].startswith("... (budget reached)")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_budget_tokens.py::test_estimate_tokens_monotonic -v`

Expected: FAIL (no `_estimate_tokens` helper exists yet).

**Step 3: Implement tokenizer-backed estimation**

In `src/tldr_swinton/output_formats.py`:
- Add `_estimate_tokens(text: str) -> int`:
  - Try `tiktoken.get_encoding("cl100k_base")` and return `len(encoding.encode(text))`.
  - On import failure, fallback to `max(1, len(text) // 4)`.
- Replace all `len(text) // 4` uses with `_estimate_tokens(text)`.
- Ensure `_apply_budget` and budgeted formatters use the new helper.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_budget_tokens.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/output_formats.py tests/test_budget_tokens.py
git commit -m "feat: token-accurate budget estimation"
```

---

### Task 4: Language-aware signatures in semantic.py

**Files:**
- Modify: `src/tldr_swinton/semantic.py`
- Test: `tests/test_semantic_signature.py` (new, guarded)

**Step 1: Write the failing test**

Create `tests/test_semantic_signature.py`:

```python
from pathlib import Path

import pytest

from tldr_swinton import semantic


@pytest.mark.skipif(not semantic.TREE_SITTER_AVAILABLE, reason="tree-sitter-typescript not available")
def test_semantic_signature_uses_language_specific_format(tmp_path: Path) -> None:
    ts = tmp_path / "mod.ts"
    ts.write_text("export function greet(name: string): string { return name }\n")

    sig = semantic._get_function_signature(ts, "greet", "typescript")
    assert sig is not None
    assert sig.startswith("function ")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_semantic_signature.py::test_semantic_signature_uses_language_specific_format -v`

Expected: FAIL (signature falls back to `def greet(...)`).

**Step 3: Implement language-aware signature fallback**

In `src/tldr_swinton/semantic.py`:
- Add helper `_get_signature_via_extractor(file_path, func_name, lang)`:
  - Use `HybridExtractor().extract()` to load `ModuleInfo`.
  - Find matching `FunctionInfo` or class method and return `func.signature()`.
- In `_get_function_signature`, if the AST-specific logic returns None, try the extractor-based signature.
- Ensure synthetic `FunctionInfo` objects set `language=lang` where applicable.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_semantic_signature.py -v`

Expected: PASS (or SKIP if tree-sitter not installed).

**Step 5: Commit**

```bash
git add src/tldr_swinton/semantic.py tests/test_semantic_signature.py
git commit -m "fix: language-aware semantic signatures"
```

---

### Task 5: Verification sweep

**Files:**
- Test: `tests/` (run targeted suite)

**Step 1: Run focused tests**

Run:
```bash
pytest tests/test_call_graph_symbol_ids.py \
       tests/test_search_respects_ignore.py \
       tests/test_budget_tokens.py \
       tests/test_semantic_signature.py -v
```

Expected: PASS (or SKIP for TS signature test if tree-sitter missing).

**Step 2: Commit if needed**

```bash
git status -sb
```

No changes expected.

---

Plan complete and saved to `docs/plans/2026-01-14-phase0-gaps-implementation-plan.md`. Two execution options:

1. Subagent-Driven (this session) — I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) — Open new session with executing-plans, batch execution with checkpoints

Which approach?
