#!/usr/bin/env python
"""Run benchmarks for token efficiency features.

This script measures token savings for compression features:
  - baselines: Full file content (baseline)
  - symbolkite: Signature-based extraction
  - edit_locality: Edit-optimized context with boundaries & invariants

Disabled features (require different benchmark types):
  - attention_pruning: Needs multi-session learning benchmark
  - context_delegation: Needs agent execution benchmark
  - coherence_verify: Needs error detection rate benchmark

Usage:
    python scripts/run_new_features_bench.py [--filter PATTERN] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tldr_bench.metrics import count_tokens
from tldr_bench.tasks.loader import load_tasks, resolve_task_file
from tldr_bench.variants import get_variant


@dataclass
class BenchResult:
    task_id: str
    variant: str
    tokens: int
    chars: int
    success: bool
    error: str | None = None


def run_variant(task: dict, variant_name: str) -> BenchResult:
    """Run a single variant on a task."""
    try:
        variant = get_variant(variant_name)
        context = variant.build_context(task)
        tokens = count_tokens(context)
        return BenchResult(
            task_id=task["id"],
            variant=variant_name,
            tokens=tokens,
            chars=len(context),
            success=True,
        )
    except Exception as e:
        return BenchResult(
            task_id=task["id"],
            variant=variant_name,
            tokens=0,
            chars=0,
            success=False,
            error=str(e),
        )


def compute_savings(baseline_tokens: int, variant_tokens: int) -> float:
    """Compute percentage token savings."""
    if baseline_tokens == 0:
        return 0.0
    return ((baseline_tokens - variant_tokens) / baseline_tokens) * 100


def run_benchmarks(tasks: list[dict], filter_pattern: str | None = None) -> dict:
    """Run all benchmarks and compute results."""
    results = []
    summaries = {}

    for task in tasks:
        if filter_pattern and filter_pattern not in task["id"]:
            continue

        task_results = {}
        variants = task.get("variants", ["baselines", "symbolkite"])

        for variant in variants:
            result = run_variant(task, variant)
            task_results[variant] = result
            results.append(result)

        # Compute savings vs baseline
        if "baselines" in task_results and task_results["baselines"].success:
            baseline = task_results["baselines"].tokens
            for variant, result in task_results.items():
                if variant != "baselines" and result.success:
                    savings = compute_savings(baseline, result.tokens)
                    key = f"{task['id']}:{variant}"
                    summaries[key] = {
                        "task_id": task["id"],
                        "variant": variant,
                        "baseline_tokens": baseline,
                        "variant_tokens": result.tokens,
                        "savings_percent": round(savings, 2),
                    }

    return {
        "results": results,
        "summaries": summaries,
    }


def print_results(data: dict, as_json: bool = False):
    """Print benchmark results."""
    if as_json:
        output = {
            "results": [
                {
                    "task_id": r.task_id,
                    "variant": r.variant,
                    "tokens": r.tokens,
                    "chars": r.chars,
                    "success": r.success,
                    "error": r.error,
                }
                for r in data["results"]
            ],
            "summaries": data["summaries"],
        }
        print(json.dumps(output, indent=2))
        return

    print("\n" + "=" * 70)
    print("TOKEN EFFICIENCY BENCHMARK RESULTS")
    print("=" * 70)

    # Group results by task
    by_task: dict[str, list[BenchResult]] = {}
    for result in data["results"]:
        by_task.setdefault(result.task_id, []).append(result)

    for task_id, results in sorted(by_task.items()):
        print(f"\n### {task_id}")
        print("-" * 50)

        # Find baseline
        baseline = next((r for r in results if r.variant == "baselines"), None)
        baseline_tokens = baseline.tokens if baseline and baseline.success else 0

        for result in sorted(results, key=lambda r: r.variant):
            if result.success:
                savings = compute_savings(baseline_tokens, result.tokens) if baseline_tokens > 0 else 0
                status = f"{result.tokens:,} tokens"
                if result.variant != "baselines":
                    if savings > 0:
                        status += f" ({savings:.1f}% savings)"
                    elif savings < 0:
                        status += f" ({-savings:.1f}% MORE tokens)"
            else:
                status = f"FAILED: {result.error}"

            print(f"  {result.variant:20s}: {status}")

    # Summary by variant type
    print("\n" + "=" * 70)
    print("SUMMARY BY VARIANT")
    print("=" * 70)

    variant_stats: dict[str, list[float]] = {}
    for summary in data["summaries"].values():
        variant = summary["variant"]
        variant_stats.setdefault(variant, []).append(summary["savings_percent"])

    for variant, savings_list in sorted(variant_stats.items()):
        avg_savings = sum(savings_list) / len(savings_list) if savings_list else 0
        min_savings = min(savings_list) if savings_list else 0
        max_savings = max(savings_list) if savings_list else 0
        print(f"  {variant:20s}: avg {avg_savings:6.1f}% | min {min_savings:6.1f}% | max {max_savings:6.1f}% ({len(savings_list)} tasks)")

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run token efficiency benchmarks")
    parser.add_argument("--filter", help="Filter tasks by ID pattern")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--tasks", default="track_new_features", help="Task file to use")
    args = parser.parse_args()

    task_file = resolve_task_file(args.tasks)
    tasks = load_tasks(task_file)

    print(f"Loading {len(tasks)} tasks from {task_file}")

    data = run_benchmarks(tasks, args.filter)
    print_results(data, args.json)


if __name__ == "__main__":
    main()
