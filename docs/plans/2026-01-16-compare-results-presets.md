# Compare Results Presets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gfb` (Implement tldrs benchmark tracks) — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Add preset/default comparison modes to `tldr-bench/scripts/compare_results.py` so users can run one command without listing all variant files.

**Architecture:** Extend `compare_results.py` CLI to accept `--track` preset(s) that expand to baseline + common variants. Keep explicit `--baseline/--variants` working. Implement presets in the script (simple mapping to result file paths). Add tests in `tldr-bench/tests/test_compare_results_cli.py` that verify preset expansion outputs a valid JSON summary with the expected variants.

**Tech Stack:** Python, argparse, JSON, tests.

### Task 1: Add preset logic + tests

**Files:**
- Modify: `tldr-bench/scripts/compare_results.py`
- Create: `tldr-bench/tests/test_compare_results_cli.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
import json
import subprocess


def test_compare_results_track_preset(tmp_path: Path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    baseline = results_dir / "official_datasets_context_baselines.jsonl"
    variant_a = results_dir / "official_datasets_context_symbolkite.jsonl"
    variant_b = results_dir / "official_datasets_context_cassette.jsonl"

    baseline.write_text('{"task_id":"t1","context_tokens":10,"total_tokens_total":100}\n', encoding="utf-8")
    variant_a.write_text('{"task_id":"t1","context_tokens":5,"total_tokens_total":60}\n', encoding="utf-8")
    variant_b.write_text('{"task_id":"t1","context_tokens":6,"total_tokens_total":70}\n', encoding="utf-8")

    cmd = [
        "uv", "run", "python",
        "tldr-bench/scripts/compare_results.py",
        "--track", "dataset-context",
        "--results-dir", str(results_dir),
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    variants = [row["variant"] for row in data]
    assert str(variant_a) in variants
    assert str(variant_b) in variants
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/sma/tldr-swinton && PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_compare_results_cli.py::test_compare_results_track_preset -q`
Expected: FAIL (unknown args / missing preset logic).

**Step 3: Implement preset logic**

- Add CLI args:
  - `--track` (choices: `dataset-context` for now)
  - `--results-dir` (default `tldr-bench/results`)
- Map `dataset-context` to:
  - baseline: `official_datasets_context_baselines.jsonl`
  - variants: `official_datasets_context_symbolkite.jsonl`, `official_datasets_context_cassette.jsonl`, `official_datasets_context_coveragelens.jsonl`
- If `--track` is provided, ignore explicit `--baseline/--variants` unless also set (prefer explicit if provided).

**Step 4: Run tests to verify they pass**

Run: `cd /Users/sma/tldr-swinton && PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_compare_results_cli.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/scripts/compare_results.py tldr-bench/tests/test_compare_results_cli.py
git commit -m "feat: add compare_results presets"
```

### Task 2: Document preset usage

**Files:**
- Modify: `tldr-bench/README.md`

**Step 1: Update README**

Add example:

```
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/compare_results.py \
  --track dataset-context --json
```

**Step 2: Commit**

```bash
git add tldr-bench/README.md
git commit -m "docs: document compare_results presets"
```

---

Plan complete and saved to `docs/plans/2026-01-16-compare-results-presets.md`.
Two execution options:
1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
