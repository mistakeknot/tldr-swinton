# DiffLens Eval + Shared Fixture Repo Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** [none] (no bead provided)

**Goal:** Add a cached synthetic repo for standalone evals and add a new DiffLens eval using it.

**Architecture:** Create `evals/fixtures/fixture_repo.py` to build a cached git template repo. Update evals to copy from the template. Add `evals/difflens_eval.py` and minimal tests for the fixture helper.

**Tech Stack:** Python 3, git CLI, pytest, tiktoken (optional)

### Task 1: Add failing tests for fixture helper

**Files:**
- Create: `tests/test_eval_fixtures.py`

**Step 1: Write failing test**

```python
from evals.fixtures.fixture_repo import ensure_fixture_repo

def test_fixture_repo_created(tmp_path):
    repo = ensure_fixture_repo(base_dir=tmp_path)
    assert (repo / ".git").exists()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eval_fixtures.py::test_fixture_repo_created -q`
Expected: FAIL (module or function missing)

**Step 3: Commit**

```bash
git add tests/test_eval_fixtures.py
git commit -m "test: add fixture repo coverage"
```

### Task 2: Implement cached fixture repo helper

**Files:**
- Create: `evals/fixtures/fixture_repo.py`
- Create: `evals/fixtures/__init__.py`

**Step 1: Implement `ensure_fixture_repo`**

```python
# Build template repo under evals/fixtures/.cache (or base_dir)
# Include baseline files for Python/TS/Rust + semantic search fixtures
# Create initial commit
```

**Step 2: Implement `copy_fixture_repo`**

```python
# Copy template to temp workdir for each eval
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_eval_fixtures.py -q`
Expected: PASS

**Step 4: Commit**

```bash
git add evals/fixtures
git commit -m "feat: add cached eval fixture repo"
```

### Task 3: Update standalone evals to use fixture repo

**Files:**
- Modify: `evals/token_efficiency_eval.py`
- Modify: `evals/semantic_search_eval.py`
- Modify: `evals/agent_workflow_eval.py`
- Modify: `evals/vhs_eval.py` (if needed)

**Step 1: Import fixture helper**

```python
from evals.fixtures.fixture_repo import copy_fixture_repo
```

**Step 2: Replace ad‑hoc temp setup with fixture copy**

```python
repo_dir = copy_fixture_repo(tmp_path)
```

**Step 3: Run one eval script**

Run: `python evals/token_efficiency_eval.py`
Expected: PASS/summary output

**Step 4: Commit**

```bash
git add evals/*.py
git commit -m "feat: reuse cached fixture repo for evals"
```

### Task 4: Add DiffLens eval

**Files:**
- Create: `evals/difflens_eval.py`
- Update: `evals/EVALS.md`

**Step 1: Implement diff scenario and metrics**

```python
# modify fixture repo workdir to create diff hunks
# call get_diff_context(...) to get pack
# compute token savings + diff-hit
```

**Step 2: Run difflens eval**

Run: `python evals/difflens_eval.py`
Expected: PASS/summary output

**Step 3: Commit**

```bash
git add evals/difflens_eval.py evals/EVALS.md
git commit -m "feat: add difflens eval"
```

### Task 5: Full verification

**Files:**
- None

**Step 1: Run tests**

Run: `python -m pytest tests -q`
Expected: PASS

