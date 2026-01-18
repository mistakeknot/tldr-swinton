# Cassette Variant (tldrs-vhs CLI) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gfb` (Implement tldrs benchmark tracks) — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Implement the cassette variant in tldr-bench to call `tldrs context --output vhs`, returning ref + summary + preview for dataset_context benchmarking.

**Architecture:** Add a CLI-backed cassette variant that shells out to `tldrs` with `--output vhs`, using the task’s entry/depth/format/budget/language. Prefer `tldrs` on PATH; fallback to `python -m tldr_swinton.cli` within the current interpreter. Return stdout from the CLI (ref + summary + preview) as the context string used for token counting.

**Tech Stack:** Python, subprocess, tldr_swinton CLI, tldr-bench variants.

### Task 1: Add cassette variant (CLI-backed)

**Files:**
- Modify: `tldr-bench/tldr_bench/variants/cassette.py`
- Create: `tldr-bench/tests/test_cassette_variant.py`

**Step 1: Write the failing test**

```python
from types import SimpleNamespace

import pytest

from tldr_bench.variants import cassette


def test_cassette_build_context_uses_tldrs_cli(monkeypatch):
    calls = {}

    def fake_which(name):
        return "/usr/local/bin/tldrs" if name == "tldrs" else None

    def fake_run(cmd, capture_output, text, env, check):
        calls["cmd"] = cmd
        calls["env"] = env
        return SimpleNamespace(stdout="vhs://abc\n# Summary: test\n# Preview:\nline\n", stderr="", returncode=0)

    monkeypatch.setattr(cassette.shutil, "which", fake_which)
    monkeypatch.setattr(cassette.subprocess, "run", fake_run)

    task = {
        "entry": "src/tldr_swinton/engines/symbolkite.py:get_relevant_context",
        "depth": 1,
        "language": "python",
        "budget": 123,
        "context_format": "text",
        "project": ".",
    }

    out = cassette.build_context(task)

    assert out.startswith("vhs://abc")
    assert calls["cmd"][0] == "tldrs"
    assert "--output" in calls["cmd"]
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/sma/tldr-swinton && PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_cassette_variant.py::test_cassette_build_context_uses_tldrs_cli -q`
Expected: FAIL with `NotImplementedError` (or import errors) from `cassette.build_context`.

**Step 3: Write minimal implementation**

```python
# tldr-bench/tldr_bench/variants/cassette.py
import os
import shutil
import subprocess
import sys

from . import resolve_project_root

VARIANT_ID = "cassette"


def _resolve_tldrs_cmd() -> list[str]:
    if shutil.which("tldrs"):
        return ["tldrs"]
    return [sys.executable, "-m", "tldr_swinton.cli"]


def build_context(task: dict) -> str:
    entry = task.get("entry", "")
    if not entry:
        raise ValueError("task.entry is required")

    project = resolve_project_root(task)
    depth = task.get("depth", 2)
    language = task.get("language", "python")
    budget = task.get("budget")
    fmt = task.get("context_format", "text")

    cmd = _resolve_tldrs_cmd() + [
        "context",
        entry,
        "--project",
        str(project),
        "--depth",
        str(depth),
        "--format",
        fmt,
        "--lang",
        language,
        "--output",
        "vhs",
    ]
    if budget is not None:
        cmd += ["--budget", str(budget)]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "tldrs context failed")

    return result.stdout.strip()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/sma/tldr-swinton && PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_cassette_variant.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/variants/cassette.py tldr-bench/tests/test_cassette_variant.py
git commit -m "feat: add cassette variant via tldrs vhs CLI"
```

### Task 2: Run cassette + coveragelens dataset-context benchmark

**Files:**
- Modify: `tldr-bench/results/official_datasets_context_cassette.jsonl`
- Modify: `tldr-bench/results/official_datasets_context_coveragelens.jsonl`

**Step 1: Run cassette variant**

Run:
```bash
cd /Users/sma/tldr-swinton
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py \
  --tasks track_dataset_context \
  --variant cassette \
  --print-results \
  --results-file tldr-bench/results/official_datasets_context_cassette.jsonl
```
Expected: `status=completed` for dataset-ctx-001.

**Step 2: Run coveragelens variant**

Run:
```bash
cd /Users/sma/tldr-swinton
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py \
  --tasks track_dataset_context \
  --variant coveragelens \
  --print-results \
  --results-file tldr-bench/results/official_datasets_context_coveragelens.jsonl
```
Expected: `status=completed` for dataset-ctx-001.

**Step 3: Summarize savings vs baseline**

Run:
```bash
cd /Users/sma/tldr-swinton
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/summarize_results.py \
  --baseline tldr-bench/results/official_datasets_context_baselines.jsonl \
  --variants tldr-bench/results/official_datasets_context_cassette.jsonl \
             tldr-bench/results/official_datasets_context_coveragelens.jsonl
```
Expected: printed token totals and savings for cassette + coveragelens compared to baseline.

**Step 4: Commit**

```bash
git add tldr-bench/results/official_datasets_context_cassette.jsonl \
        tldr-bench/results/official_datasets_context_coveragelens.jsonl
git commit -m "results: add cassette and coveragelens dataset-context runs"
```

---

Plan complete and saved to `docs/plans/2026-01-16-cassette-variant-vhs-cli.md`.
Two execution options:
1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
