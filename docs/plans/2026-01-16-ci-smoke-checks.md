# CI Smoke Checks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gfb` (Implement tldrs benchmark tracks) — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Add GitHub Actions CI using uv and run a small smoke test for tldr-bench helpers (compare_results + cassette variant). 

**Architecture:** Add `.github/workflows/ci.yml` that sets up Python + uv, installs repo, and runs a focused pytest subset. The tests will run `tldr-bench/tests/test_compare_results_cli.py` and `tldr-bench/tests/test_cassette_variant.py` only to keep CI fast and deterministic.

**Tech Stack:** GitHub Actions, uv, pytest.

### Task 1: Add CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Write the failing test**

Not applicable (CI config). Use local validation by running the same pytest command.

**Step 2: Add workflow file**

```yaml
name: CI
on:
  push:
  pull_request:

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Install deps
        run: |
          export PATH="$HOME/.cargo/bin:$PATH"
          uv sync --extra semantic-ollama
      - name: Smoke tests (tldr-bench helpers)
        run: |
          export PATH="$HOME/.cargo/bin:$PATH"
          PYTHONPATH=tldr-bench uv run python -m pytest \
            tldr-bench/tests/test_compare_results_cli.py \
            tldr-bench/tests/test_cassette_variant.py -q
```

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add tldr-bench smoke checks"
```

---

Plan complete and saved to `docs/plans/2026-01-16-ci-smoke-checks.md`.
Two execution options:
1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
