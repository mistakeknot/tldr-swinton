# DiffLens TypeScript Fixture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** N/A (Task reference)

**Goal:** Add a TypeScript synthetic fixture to DiffLens eval so the runner tests Python + TS fixtures.

**Architecture:** Add a TS fixture generator alongside the existing Python generator in `evals/difflens_eval.py`, write a temp repo with `.ts` files, and add eval results for TS (symbol mapping, token savings, diff lines/windowed code). Update tests to validate TS fixture generation and repo writing.

**Tech Stack:** Python, pytest, git

### Task 1: Add failing tests for TS fixture generation

**Files:**
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_ts_fixture_sources() -> None:
    module = _load_eval_module()
    sources = module._build_ts_fixture_sources()
    assert isinstance(sources, dict)
    assert len(sources) >= 10
    total_lines = sum(source.count("\n") for source in sources.values())
    assert total_lines >= 1500
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_ts_fixture_sources -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Implement `_build_ts_fixture_sources` in `evals/difflens_eval.py` returning a dict of `.ts` filenames to source strings.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_ts_fixture_sources -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_difflens_eval.py evals/difflens_eval.py
git commit -m "test: add TS fixture expectations"
```

### Task 2: Add TS repo writer and eval results

**Files:**
- Modify: `evals/difflens_eval.py`
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_ts_fixture_written(tmp_path: Path) -> None:
    module = _load_eval_module()
    module._write_ts_repo(tmp_path)
    files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".ts")
    assert len(files) >= 10
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_ts_fixture_written -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Add `_write_ts_repo` using `_build_ts_fixture_sources`, then update `run_eval()` to generate TS results (symbol mapping + token savings). Use `language="typescript"` when calling `get_diff_context` for TS.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_ts_fixture_written -v`
Expected: PASS

**Step 5: Commit**

```bash
git add evals/difflens_eval.py tests/test_difflens_eval.py
git commit -m "feat: add TS difflens eval"
```

### Task 3: Verify full difflens eval tests

**Files:**
- Test: `tests/test_difflens_eval.py`

**Step 1: Run full tests**

Run: `pytest tests/test_difflens_eval.py -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status --porcelain
```
