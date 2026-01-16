from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_METRICS = ("context_tokens", "total_tokens_total")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
    results: list[dict[str, Any]] = []
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
