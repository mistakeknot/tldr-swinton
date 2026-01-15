# DiffLens Deps Baseline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** N/A (Task reference)

**Goal:** Add a “diff files + direct deps” baseline to the DiffLens eval output for more realistic measurement.

**Architecture:** Parse direct imports from changed files in the fixture repo, resolve local files (Python and TS), and sum tokens for diff files + resolved deps. Report both baselines in eval output while keeping existing checks. Keep logic self-contained in `evals/difflens_eval.py` and add tests for dependency resolution in the eval module.

**Tech Stack:** Python, pytest, git

### Task 1: Add failing tests for dependency resolution

**Files:**
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_resolve_py_deps(tmp_path: Path) -> None:
    module = _load_eval_module()
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    deps = module._resolve_py_deps(tmp_path, {"a.py"})
    assert "b.py" in deps
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_resolve_py_deps -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Add `_resolve_py_deps` helper in `evals/difflens_eval.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_resolve_py_deps -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_difflens_eval.py evals/difflens_eval.py
git commit -m "test: add dep baseline expectations"
```

### Task 2: Add TS dependency resolution tests

**Files:**
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_resolve_ts_deps(tmp_path: Path) -> None:
    module = _load_eval_module()
    (tmp_path / "a.ts").write_text("import { b } from './b';\n")
    (tmp_path / "b.ts").write_text("export const b = 1;\n")
    deps = module._resolve_ts_deps(tmp_path, {"a.ts"})
    assert "b.ts" in deps
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_resolve_ts_deps -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Add `_resolve_ts_deps` helper in `evals/difflens_eval.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_resolve_ts_deps -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_difflens_eval.py evals/difflens_eval.py
git commit -m "test: add TS dep baseline expectations"
```

### Task 3: Integrate deps baseline into eval output

**Files:**
- Modify: `evals/difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_baseline_includes_deps(tmp_path: Path) -> None:
    module = _load_eval_module()
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    tokens_full = module._sum_tokens(tmp_path, {"a.py"})
    tokens_with_deps = module._sum_tokens(tmp_path, {"a.py"}, include_deps=True)
    assert tokens_with_deps > tokens_full
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_baseline_includes_deps -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Add helper `_sum_tokens` to optionally include deps, and update `_run_fixture_eval` to compute and report diff-only vs diff+deps savings.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_baseline_includes_deps -v`
Expected: PASS

**Step 5: Commit**

```bash
git add evals/difflens_eval.py tests/test_difflens_eval.py
git commit -m "feat: add deps baseline to difflens eval"
```

### Task 4: Verify full difflens eval tests

**Files:**
- Test: `tests/test_difflens_eval.py`

**Step 1: Run full tests**

Run: `pytest tests/test_difflens_eval.py -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status --porcelain
```
