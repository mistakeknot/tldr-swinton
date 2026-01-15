# DiffLens Large Multi-File Synthetic Fixture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** N/A (Task reference)

**Goal:** Expand the default DiffLens synthetic fixture to a large multi-file repo (~25+ files, 5k+ lines) with richer call graphs and light class usage.

**Architecture:** Replace the current small multi-file fixture builder with a parameterized generator that emits multiple modules (core, models, utils, services) and a synthetic call graph. Keep changes localized to `evals/difflens_eval.py` and update tests to validate the larger fixture (file count + line count).

**Tech Stack:** Python, pytest, git

### Task 1: Update tests to expect large multi-file fixture

**Files:**
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_large_multifile_fixture_sources() -> None:
    module = _load_eval_module()
    sources = module._build_multifile_fixture_sources()
    assert isinstance(sources, dict)
    assert len(sources) >= 25
    total_lines = sum(source.count("\n") for source in sources.values())
    assert total_lines >= 5000
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_large_multifile_fixture_sources -v`
Expected: FAIL with count mismatch

**Step 3: Write minimal implementation**

Adjust fixture builder in `evals/difflens_eval.py` to generate >=25 files and >=5000 lines.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_large_multifile_fixture_sources -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_difflens_eval.py evals/difflens_eval.py
git commit -m "test: expect large difflens fixture"
```

### Task 2: Expand the multi-file fixture generator

**Files:**
- Modify: `evals/difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_multifile_fixture_written_large(tmp_path: Path) -> None:
    module = _load_eval_module()
    module._write_multifile_repo(tmp_path)
    py_files = [p for p in tmp_path.iterdir() if p.suffix == ".py"]
    assert len(py_files) >= 25
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_multifile_fixture_written_large -v`
Expected: FAIL with count mismatch

**Step 3: Write minimal implementation**

Update `_build_multifile_fixture_sources` to generate module families (e.g., `core_*.py`, `models_*.py`, `services_*.py`, `utils_*.py`) with larger bodies and light class usage. Update `_write_multifile_repo` to write all files.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_multifile_fixture_written_large -v`
Expected: PASS

**Step 5: Commit**

```bash
git add evals/difflens_eval.py tests/test_difflens_eval.py
git commit -m "feat: expand difflens fixture to large multifile"
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
