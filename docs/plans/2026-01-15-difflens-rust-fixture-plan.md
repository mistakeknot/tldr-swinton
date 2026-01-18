# DiffLens Rust Fixture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** N/A (Task reference)

**Goal:** Add a large Rust synthetic fixture to DiffLens eval so the runner tests Python + TS + Rust repos.

**Architecture:** Add a Rust fixture generator and repo writer in `evals/difflens_eval.py`, producing 25+ `.rs` files with modules, structs, and functions. Add simple `mod` imports to enable direct deps resolution. Update eval to run Rust fixture with `language="rust"`. Extend tests to validate Rust fixture generation and repo writing.

**Tech Stack:** Python, pytest, git

### Task 1: Add failing tests for Rust fixture generation

**Files:**
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_rust_fixture_sources() -> None:
    module = _load_eval_module()
    sources = module._build_rust_fixture_sources()
    assert isinstance(sources, dict)
    assert len(sources) >= 25
    total_lines = sum(source.count("\n") for source in sources.values())
    assert total_lines >= 5000
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_rust_fixture_sources -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Implement `_build_rust_fixture_sources` in `evals/difflens_eval.py` returning a dict of `.rs` filenames to source strings.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_rust_fixture_sources -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_difflens_eval.py evals/difflens_eval.py
git commit -m "test: add Rust fixture expectations"
```

### Task 2: Add Rust repo writer and eval results

**Files:**
- Modify: `evals/difflens_eval.py`
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_rust_fixture_written(tmp_path: Path) -> None:
    module = _load_eval_module()
    module._write_rust_repo(tmp_path)
    files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".rs")
    assert len(files) >= 25
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_rust_fixture_written -v`
Expected: FAIL with "attribute missing" (function not defined)

**Step 3: Write minimal implementation**

Add `_write_rust_repo` using `_build_rust_fixture_sources`, update `run_eval()` to generate Rust results. Use `language="rust"` when calling `get_diff_context` for Rust.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_rust_fixture_written -v`
Expected: PASS

**Step 5: Commit**

```bash
git add evals/difflens_eval.py tests/test_difflens_eval.py
git commit -m "feat: add Rust difflens eval"
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
