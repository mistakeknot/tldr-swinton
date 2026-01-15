# DiffLens Multi-File Synthetic Eval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** N/A (Task reference)

**Goal:** Make DiffLens eval default to a multi-file synthetic fixture while keeping `--repo` optional.

**Architecture:** Replace the single-file fixture builder with a multi-file builder that writes several Python files into the temp repo, then adjust eval checks to use those files. Update tests to assert the new fixture shape.

**Tech Stack:** Python, pytest, git

### Task 1: Update tests for multi-file fixture

**Files:**
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_multifile_fixture_sources() -> None:
    module = _load_eval_module()
    sources = module._build_multifile_fixture_sources()
    assert isinstance(sources, dict)
    assert len(sources) >= 2
    total_lines = sum(src.count("\n") for src in sources.values())
    assert total_lines >= 300
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_multifile_fixture_sources -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Implement `_build_multifile_fixture_sources` in `evals/difflens_eval.py` returning a dict of filenames to source strings.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_multifile_fixture_sources -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_difflens_eval.py evals/difflens_eval.py
git commit -m "test: add multifile fixture expectation"
```

### Task 2: Switch eval default to multi-file synthetic repo

**Files:**
- Modify: `evals/difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_multifile_fixture_written(tmp_path: Path) -> None:
    module = _load_eval_module()
    module._write_multifile_repo(tmp_path)
    files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".py")
    assert len(files) >= 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_multifile_fixture_written -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Add `_write_multifile_repo` to use `_build_multifile_fixture_sources`, update `run_eval()` to use it for the default fixture, and adjust token savings to sum across changed files. Keep the windowed diff check as-is and keep `--repo` optional.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_multifile_fixture_written -v`
Expected: PASS

**Step 5: Commit**

```bash
git add evals/difflens_eval.py tests/test_difflens_eval.py
git commit -m "feat: switch difflens eval to multifile fixture"
```

### Task 3: Verify full test

**Files:**
- Test: `tests/test_difflens_eval.py`

**Step 1: Run full tests**

Run: `pytest tests/test_difflens_eval.py -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status --porcelain
```
