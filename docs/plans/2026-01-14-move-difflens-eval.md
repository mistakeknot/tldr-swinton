# Move DiffLens Eval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** [none] (no bead provided)

**Goal:** Remove DiffLens from tldr-bench and add a dedicated DiffLens eval under `evals/`.

**Architecture:** Delete DiffLens variant/task/docs/tests from tldr-bench, add `evals/difflens_eval.py` that runs the new `get_diff_context` path and reports token/latency metrics; update `evals/EVALS.md` with the new eval.

**Tech Stack:** Python 3, pytest

### Task 1: Add failing eval test (lightweight)

**Files:**
- Create: `tests/test_difflens_eval.py`

**Step 1: Write failing test for eval script existence**

```python
from pathlib import Path

def test_difflens_eval_exists():
    assert Path('evals/difflens_eval.py').exists()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_difflens_eval.py -q`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/test_difflens_eval.py
git commit -m "test: require difflens eval"
```

### Task 2: Remove DiffLens from tldr-bench

**Files:**
- Delete: `tldr-bench/tldr_bench/variants/difflens.py`
- Modify: `tldr-bench/tldr_bench/variants/__init__.py`
- Modify: `tldr-bench/tldr_bench/tasks/track_context.yaml`
- Modify: `tldr-bench/README.md`
- Modify: `tldr-bench/docs/VARIANTS.md`
- Modify: `tldr-bench/AGENTS.md`
- Modify: `tldr-bench/tests/test_run_bench_metadata.py`
- Modify: `tldr-bench/tests/test_static_context_runner.py`
- Modify: `tldr-bench/tests/test_router.py`

**Step 1: Remove DiffLens references from variant registry and docs**

**Step 2: Remove DiffLens tasks/tests**

**Step 3: Run tests to verify failures are resolved**

Run: `python -m pytest tldr-bench/tests/test_run_bench_metadata.py::test_variants_listed -q`
Expected: PASS

**Step 4: Commit**

```bash
git add tldr-bench
 git commit -m "chore: remove difflens from tldr-bench"
```

### Task 3: Add `evals/difflens_eval.py`

**Files:**
- Create: `evals/difflens_eval.py`
- Modify: `evals/EVALS.md`

**Step 1: Implement eval script**

```python
# Run get_diff_context on a small fixture repo/diff,
# report tokens (approx) + latency + slice counts
```

**Step 2: Update EVALS.md with usage**

**Step 3: Run tests**

Run: `python -m pytest tests/test_difflens_eval.py -q`
Expected: PASS

**Step 4: Commit**

```bash
git add evals/EVALS.md evals/difflens_eval.py tests/test_difflens_eval.py
 git commit -m "feat: add difflens eval"
```

### Task 4: Full verification

**Files:**
- None

**Step 1: Run project tests**

Run: `python -m pytest tests -q`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status --short
```

