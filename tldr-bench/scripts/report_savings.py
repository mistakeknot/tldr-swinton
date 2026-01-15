from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _index_by_task(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = row.get("task_id")
        if not task_id:
            continue
        indexed[str(task_id)] = row
    return indexed


def _savings(baseline: float, variant: float) -> float | None:
    if baseline <= 0:
        return None
    return (baseline - variant) / baseline * 100.0


def _format_row(values: list[str], widths: list[int]) -> str:
    padded = [value.ljust(widths[i]) for i, value in enumerate(values)]
    return "  ".join(padded)


def _select_metric(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--metric", default="context_tokens")
    parser.add_argument("--total-metric", default="total_tokens_median")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    baseline_rows = _load_jsonl(Path(args.baseline))
    variant_rows = _load_jsonl(Path(args.variant))
    baseline_index = _index_by_task(baseline_rows)
    variant_index = _index_by_task(variant_rows)

    results = []
    for task_id, base_row in baseline_index.items():
        variant_row = variant_index.get(task_id)
        if not variant_row:
            continue
        base_context = _select_metric(base_row, args.metric)
        var_context = _select_metric(variant_row, args.metric)
        base_total = _select_metric(base_row, args.total_metric)
        var_total = _select_metric(variant_row, args.total_metric)
        results.append(
            {
                "task_id": task_id,
                "baseline_metric": base_context,
                "variant_metric": var_context,
                "baseline_total": base_total,
                "variant_total": var_total,
                "savings_pct": _savings(base_context or 0.0, var_context or 0.0),
                "total_savings_pct": _savings(base_total or 0.0, var_total or 0.0),
            }
        )

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    headers = [
        "task_id",
        f"baseline_{args.metric}",
        f"variant_{args.metric}",
        "savings_pct",
        f"baseline_{args.total_metric}",
        f"variant_{args.total_metric}",
        "total_savings_pct",
    ]
    rows = [headers]
    for row in results:
        rows.append(
            [
                row["task_id"],
                str(row["baseline_metric"]),
                str(row["variant_metric"]),
                f"{row['savings_pct']:.1f}%" if row["savings_pct"] is not None else "n/a",
                str(row["baseline_total"]),
                str(row["variant_total"]),
                f"{row['total_savings_pct']:.1f}%" if row["total_savings_pct"] is not None else "n/a",
            ]
        )

    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    for row in rows:
        print(_format_row(row, widths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
