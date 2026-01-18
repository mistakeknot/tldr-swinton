# Compare Results Script Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gfb` (Implement tldrs benchmark tracks) — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Add a `compare_results.py` script to compute token savings vs a baseline across one or more JSONL result files, with text and `--json` output.

**Architecture:** Put core logic in a small `tldr_bench.compare_results` module to make it testable. The script in `tldr-bench/scripts/compare_results.py` will parse CLI args, call the module, and print either a human-readable table or JSON. The comparison will align tasks by `task_id` (last row wins) and compute totals for `context_tokens` and `total_tokens_total`.

**Tech Stack:** Python, argparse, JSONL parsing, tldr-bench tests.

### Task 1: Implement compare_results module + tests

**Files:**
- Create: `tldr-bench/tldr_bench/compare_results.py`
- Create: `tldr-bench/tests/test_compare_results.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from tldr_bench.compare_results import compare_results


def test_compare_results_sums_and_saves(tmp_path: Path):
    baseline = tmp_path / "baseline.jsonl"
    variant = tmp_path / "variant.jsonl"

    baseline.write_text(
        "{""task_id"":""t1"",""context_tokens"":10,""total_tokens_total"":100}\n"
        "{""task_id"":""t2"",""context_tokens"":20,""total_tokens_total"":200}\n",
        encoding="utf-8",
    )
    variant.write_text(
        "{""task_id"":""t1"",""context_tokens"":5,""total_tokens_total"":60}\n"
        "{""task_id"":""t2"",""context_tokens"":10,""total_tokens_total"":120}\n",
        encoding="utf-8",
    )

    results = compare_results(baseline, [variant])
    assert results[0]["tasks"] == 2
    assert results[0]["metrics"]["context_tokens"]["baseline"] == 30
    assert results[0]["metrics"]["context_tokens"]["variant"] == 15
    assert results[0]["metrics"]["total_tokens_total"]["baseline"] == 300
    assert results[0]["metrics"]["total_tokens_total"]["variant"] == 180
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/sma/tldr-swinton && PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_compare_results.py::test_compare_results_sums_and_saves -q`
Expected: FAIL with `ImportError` or missing function/module.

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_METRICS = ("context_tokens", "total_tokens_total")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _last_by_task(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = row.get("task_id")
        if not task_id:
            continue
        indexed[str(task_id)] = row
    return indexed


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_metric(rows: dict[str, dict[str, Any]], key: str) -> float:
    total = 0.0
    for row in rows.values():
        value = _coerce_float(row.get(key))
        if value is None:
            continue
        total += value
    return total


def compare_results(
    baseline_path: Path,
    variant_paths: list[Path],
    metrics: tuple[str, ...] = DEFAULT_METRICS,
) -> list[dict[str, Any]]:
    base_rows = _last_by_task(_load_jsonl(baseline_path))
    results = []
    for variant_path in variant_paths:
        var_rows = _last_by_task(_load_jsonl(variant_path))
        shared = {task_id: base_rows[task_id] for task_id in base_rows if task_id in var_rows}
        shared_variant = {task_id: var_rows[task_id] for task_id in shared}

        metrics_out: dict[str, dict[str, float | None]] = {}
        for metric in metrics:
            base_total = _sum_metric(shared, metric)
            var_total = _sum_metric(shared_variant, metric)
            savings = base_total - var_total
            savings_pct = (savings / base_total * 100.0) if base_total else None
            metrics_out[metric] = {
                "baseline": base_total,
                "variant": var_total,
                "savings": savings,
                "savings_pct": savings_pct,
            }

        results.append(
            {
                "variant": str(variant_path),
                "tasks": len(shared),
                "metrics": metrics_out,
            }
        )
    return results
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/sma/tldr-swinton && PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_compare_results.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/compare_results.py tldr-bench/tests/test_compare_results.py
git commit -m "feat: add compare_results helper for JSONL savings"
```

### Task 2: Add compare_results script + README usage

**Files:**
- Create: `tldr-bench/scripts/compare_results.py`
- Modify: `tldr-bench/README.md`

**Step 1: Write the failing test**

```python
from pathlib import Path

from tldr_bench.compare_results import compare_results


def test_compare_results_handles_json_output(tmp_path: Path):
    baseline = tmp_path / "baseline.jsonl"
    variant = tmp_path / "variant.jsonl"
    baseline.write_text("{""task_id"":""t1"",""context_tokens"":10,""total_tokens_total"":100}\n", encoding="utf-8")
    variant.write_text("{""task_id"":""t1"",""context_tokens"":5,""total_tokens_total"":60}\n", encoding="utf-8")

    results = compare_results(baseline, [variant])
    assert results[0]["metrics"]["total_tokens_total"]["savings"] == 40
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/sma/tldr-swinton && PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_compare_results.py::test_compare_results_handles_json_output -q`
Expected: FAIL until compare_results logic supports totals (then PASS).

**Step 3: Implement script wrapper + README update**

```python
# tldr-bench/scripts/compare_results.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tldr_bench.compare_results import compare_results


def _format_line(values, widths):
    return "  ".join(value.ljust(widths[i]) for i, value in enumerate(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--variants", nargs="+", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = compare_results(
        Path(args.baseline),
        [Path(path) for path in args.variants],
    )

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    for result in results:
        print(f"variant: {result['variant']}")
        print(f"tasks: {result['tasks']}")
        headers = ["metric", "baseline", "variant", "savings", "savings_pct"]
        rows = [headers]
        for metric, values in result["metrics"].items():
            pct = values["savings_pct"]
            rows.append(
                [
                    metric,
                    str(int(values["baseline"])),
                    str(int(values["variant"])),
                    str(int(values["savings"])),
                    f"{pct:.1f}%" if pct is not None else "n/a",
                ]
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
        for row in rows:
            print(_format_line(row, widths))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add README snippet near “Savings report”:

```
Compare results (baseline vs many variants):

PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/compare_results.py \
  --baseline tldr-bench/results/baseline.jsonl \
  --variants tldr-bench/results/symbolkite.jsonl tldr-bench/results/coveragelens.jsonl
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/sma/tldr-swinton && PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_compare_results.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/scripts/compare_results.py tldr-bench/README.md tldr-bench/tests/test_compare_results.py
git commit -m "feat: add compare_results script for baseline savings"
```

---

Plan complete and saved to `docs/plans/2026-01-16-compare-results-script.md`.
Two execution options:
1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
