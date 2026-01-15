from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tldr_bench.logger import JsonlLogger
from tldr_bench.meta import system_metadata
from tldr_bench.results import resolve_results_dir
from tldr_bench.runners.router import run_task as run_task_router
from tldr_bench.tasks import load_tasks, resolve_task_file


def _parse_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [token.strip() for token in value.split(",") if token.strip()]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(__import__("json").loads(line))
    return rows


def _extract_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {"context_tokens": None, "total_tokens_median": None}
    row = rows[0]
    return {
        "context_tokens": row.get("context_tokens"),
        "total_tokens_median": row.get("total_tokens_median"),
    }


def _savings(baseline: float | None, variant: float | None) -> float | None:
    if baseline is None or variant is None:
        return None
    if baseline <= 0:
        return None
    return (baseline - variant) / baseline * 100.0


def run_variant(tasks: list[dict[str, Any]], variant: str, run_config: dict[str, Any], out_path: Path) -> None:
    logger = JsonlLogger(out_path)
    host_metadata = system_metadata()

    for task in tasks:
        result = run_task_router(task, variant, run_config)
        result.update(host_metadata)
        if run_config.get("instance_ids"):
            result["instance_ids"] = run_config["instance_ids"]
        logger.log_with_timestamp(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="track_dataset_context")
    parser.add_argument("--baseline", default="baselines")
    parser.add_argument("--variants", default="symbolkite,difflens,cfg,dfg,pdg,slice")
    parser.add_argument("--instance-ids", default=None)
    parser.add_argument("--tokenizer-model", default=None)
    parser.add_argument("--results-dir", default=None)
    args = parser.parse_args()

    task_file = resolve_task_file(args.tasks)
    tasks = load_tasks(task_file)

    instance_ids = _parse_list(args.instance_ids)
    run_config = {
        "tokenizer_model": args.tokenizer_model,
    }
    if instance_ids:
        run_config["instance_ids"] = instance_ids

    results_root = Path(args.results_dir) if args.results_dir else resolve_results_dir()
    results_root.mkdir(parents=True, exist_ok=True)

    stamp = _timestamp()
    baseline_path = results_root / f"sweep-{stamp}-baseline.jsonl"
    run_variant(tasks, args.baseline, run_config, baseline_path)
    baseline_rows = _load_rows(baseline_path)
    baseline_metrics = _extract_metrics(baseline_rows)

    summary_rows: list[list[str]] = []
    summary_rows.append([
        "variant",
        "context_tokens",
        "total_tokens_median",
        "context_savings_pct",
        "total_savings_pct",
    ])

    for variant in _parse_list(args.variants):
        variant_path = results_root / f"sweep-{stamp}-{variant}.jsonl"
        run_variant(tasks, variant, run_config, variant_path)
        variant_rows = _load_rows(variant_path)
        variant_metrics = _extract_metrics(variant_rows)

        context_savings = _savings(
            baseline_metrics["context_tokens"],
            variant_metrics["context_tokens"],
        )
        total_savings = _savings(
            baseline_metrics["total_tokens_median"],
            variant_metrics["total_tokens_median"],
        )

        summary_rows.append([
            variant,
            str(variant_metrics["context_tokens"]),
            str(variant_metrics["total_tokens_median"]),
            f"{context_savings:.1f}%" if context_savings is not None else "n/a",
            f"{total_savings:.1f}%" if total_savings is not None else "n/a",
        ])

    widths = [max(len(row[i]) for row in summary_rows) for i in range(len(summary_rows[0]))]
    for row in summary_rows:
        padded = [row[i].ljust(widths[i]) for i in range(len(row))]
        print("  ".join(padded))

    print(f"\nBaseline: {baseline_path}")
    print(f"Results dir: {results_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
