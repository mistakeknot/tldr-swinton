#!/usr/bin/env python
"""Run benchmarks for the new token efficiency features.

This script measures different aspects of context optimization:

COMPRESSION FEATURES (measure token savings):
  - symbolkite: Signature-based extraction
  - edit_locality: Edit-optimized context with boundaries

LEARNING FEATURES (require historical data):
  - attention_pruning: Prunes based on past usage patterns
    NOTE: Shows ~0% savings without usage history

WORKFLOW FEATURES (different paradigm, not compression):
  - context_delegation: Returns retrieval PLAN, not context
    NOTE: Plan size is not comparable to context size

QUALITY FEATURES (add tokens for error prevention):
  - coherence_verify: Adds cross-file consistency checks
    NOTE: Increases tokens vs symbolkite (by design)

Usage:
    python scripts/run_new_features_bench.py [--filter PATTERN] [--json]
    python scripts/run_new_features_bench.py --category compression
    python scripts/run_new_features_bench.py --category learning
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tldr_bench.metrics import count_tokens
from tldr_bench.tasks.loader import load_tasks, resolve_task_file
from tldr_bench.variants import get_variant


# Feature categories for proper comparison
FEATURE_CATEGORIES = {
    "compression": {
        "variants": ["baselines", "symbolkite", "edit_locality"],
        "description": "Token savings via smarter context extraction",
        "comparable": True,
        "baseline": "baselines",
    },
    "learning": {
        "variants": ["symbolkite", "attention_pruning"],
        "description": "Token savings via learned usage patterns (requires history)",
        "comparable": True,
        "baseline": "symbolkite",
        "warning": "Without usage history, attention_pruning = symbolkite",
    },
    "workflow": {
        "variants": ["symbolkite", "context_delegation"],
        "description": "Retrieval plan vs upfront context (NOT comparable)",
        "comparable": False,
        "note": "context_delegation returns a PLAN, not context. "
                "True savings require end-to-end agent execution.",
    },
    "quality": {
        "variants": ["symbolkite", "coherence_verify"],
        "description": "Error prevention via cross-file checks (ADDS tokens)",
        "comparable": False,
        "note": "coherence_verify adds tokens ON TOP of symbolkite. "
                "Value is in error detection, not compression.",
    },
}


@dataclass
class BenchResult:
    task_id: str
    variant: str
    tokens: int
    chars: int
    success: bool
    category: str = ""
    error: str | None = None


@dataclass
class CategorySummary:
    category: str
    description: str
    comparable: bool
    results: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_variant(task: dict, variant_name: str) -> BenchResult:
    """Run a single variant on a task."""
    category = task.get("category", task.get("type", "unknown"))
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
            category=category,
        )
    except Exception as e:
        return BenchResult(
            task_id=task["id"],
            variant=variant_name,
            tokens=0,
            chars=0,
            success=False,
            category=category,
            error=str(e),
        )


def compute_savings(baseline_tokens: int, variant_tokens: int) -> float:
    """Compute percentage token savings."""
    if baseline_tokens == 0:
        return 0.0
    return ((baseline_tokens - variant_tokens) / baseline_tokens) * 100


def run_benchmarks(
    tasks: list[dict],
    filter_pattern: str | None = None,
    category_filter: str | None = None,
) -> dict:
    """Run all benchmarks and compute results."""
    results = []
    summaries = {}
    category_summaries: dict[str, CategorySummary] = {}

    for task in tasks:
        if filter_pattern and filter_pattern not in task["id"]:
            continue

        task_category = task.get("category", task.get("type", "unknown"))
        if category_filter and task_category != category_filter:
            continue

        task_results = {}
        variants = task.get("variants", ["baselines", "symbolkite"])

        for variant in variants:
            result = run_variant(task, variant)
            task_results[variant] = result
            results.append(result)

        # Determine appropriate baseline for this category
        cat_info = FEATURE_CATEGORIES.get(task_category, {})
        baseline_variant = cat_info.get("baseline", "baselines")

        # Compute savings vs appropriate baseline
        if baseline_variant in task_results and task_results[baseline_variant].success:
            baseline = task_results[baseline_variant].tokens
            for variant, result in task_results.items():
                if variant != baseline_variant and result.success:
                    savings = compute_savings(baseline, result.tokens)
                    key = f"{task['id']}:{variant}"
                    summaries[key] = {
                        "task_id": task["id"],
                        "variant": variant,
                        "category": task_category,
                        "baseline_variant": baseline_variant,
                        "baseline_tokens": baseline,
                        "variant_tokens": result.tokens,
                        "savings_percent": round(savings, 2),
                        "comparable": cat_info.get("comparable", True),
                    }

    return {
        "results": results,
        "summaries": summaries,
    }


def print_results(data: dict, as_json: bool = False):
    """Print benchmark results with proper category awareness."""
    if as_json:
        # Convert dataclass results to dicts
        output = {
            "results": [
                {
                    "task_id": r.task_id,
                    "variant": r.variant,
                    "tokens": r.tokens,
                    "chars": r.chars,
                    "success": r.success,
                    "category": r.category,
                    "error": r.error,
                }
                for r in data["results"]
            ],
            "summaries": data["summaries"],
            "feature_categories": FEATURE_CATEGORIES,
        }
        print(json.dumps(output, indent=2))
        return

    print("\n" + "=" * 80)
    print("NEW FEATURES BENCHMARK RESULTS")
    print("=" * 80)

    # Print category legend
    print("\nFEATURE CATEGORIES:")
    for cat, info in FEATURE_CATEGORIES.items():
        comparable_tag = "COMPARABLE" if info["comparable"] else "NOT COMPARABLE"
        print(f"  {cat:15s}: {info['description']} [{comparable_tag}]")
        if "warning" in info:
            print(f"                  WARNING: {info['warning']}")
        if "note" in info:
            print(f"                  NOTE: {info['note']}")

    # Group results by category
    by_category: dict[str, dict[str, list[BenchResult]]] = {}
    for result in data["results"]:
        cat = result.category
        task_id = result.task_id
        by_category.setdefault(cat, {}).setdefault(task_id, []).append(result)

    for category in ["compression", "learning", "workflow", "quality", "combined", "all"]:
        if category not in by_category:
            continue

        cat_info = FEATURE_CATEGORIES.get(category, {})
        comparable = cat_info.get("comparable", True)

        print(f"\n{'=' * 80}")
        print(f"CATEGORY: {category.upper()}")
        if not comparable:
            print("  ⚠️  Results in this category are NOT directly comparable")
        print("=" * 80)

        for task_id, results in sorted(by_category[category].items()):
            print(f"\n### {task_id}")
            print("-" * 60)

            # Find appropriate baseline
            baseline_variant = cat_info.get("baseline", "baselines")
            baseline = next(
                (r for r in results if r.variant == baseline_variant and r.success),
                None
            )
            # Fall back to baselines if category baseline not found
            if not baseline:
                baseline = next(
                    (r for r in results if r.variant == "baselines" and r.success),
                    None
                )
            baseline_tokens = baseline.tokens if baseline else 0

            for result in sorted(results, key=lambda r: r.variant):
                if result.success:
                    status = f"{result.tokens:,} tokens"
                    if baseline_tokens > 0 and result.variant not in ("baselines", baseline_variant):
                        savings = compute_savings(baseline_tokens, result.tokens)
                        if savings > 0:
                            if comparable:
                                status += f" ({savings:.1f}% savings)"
                            else:
                                status += f" ({savings:.1f}% vs {baseline_variant} - NOT COMPARABLE)"
                        elif savings < 0:
                            status += f" ({-savings:.1f}% MORE tokens)"
                    elif result.variant == baseline_variant:
                        status += " [baseline for category]"
                else:
                    status = f"FAILED: {result.error}"

                print(f"  {result.variant:20s}: {status}")

    # Summary by variant type (only for comparable categories)
    print("\n" + "=" * 80)
    print("SUMMARY BY VARIANT (Comparable categories only)")
    print("=" * 80)

    variant_stats: dict[str, list[float]] = {}
    for summary in data["summaries"].values():
        # Only include results from comparable categories
        if not summary.get("comparable", True):
            continue
        # Also check category is explicitly comparable
        cat = summary.get("category", "")
        cat_info = FEATURE_CATEGORIES.get(cat, {})
        if not cat_info.get("comparable", True):
            continue
        variant = summary["variant"]
        variant_stats.setdefault(variant, []).append(summary["savings_percent"])

    if variant_stats:
        for variant, savings_list in sorted(variant_stats.items()):
            avg_savings = sum(savings_list) / len(savings_list) if savings_list else 0
            min_savings = min(savings_list) if savings_list else 0
            max_savings = max(savings_list) if savings_list else 0
            print(
                f"  {variant:20s}: avg {avg_savings:6.1f}% | "
                f"min {min_savings:6.1f}% | max {max_savings:6.1f}% "
                f"({len(savings_list)} tasks)"
            )
    else:
        print("  No comparable compression results.")

    # Warnings section
    print("\n" + "=" * 80)
    print("IMPORTANT NOTES")
    print("=" * 80)
    print("""
  - context_delegation: Token counts show PLAN SIZE only. The plan tells
    agents what to retrieve - actual savings require agent execution.

  - coherence_verify: ADDS tokens to symbolkite for error prevention.
    Any "savings" vs baselines come from symbolkite, not coherence.

  - attention_pruning: Requires usage history. Cold-start benchmarks
    show ~0% savings because there's no history to inform pruning.

  - edit_locality: Compare to symbolkite, not baselines. It includes
    function body + boundaries, so it's larger than pure signatures.
""")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run new features benchmarks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Categories:
  compression  - Token savings via smarter extraction (symbolkite, edit_locality)
  learning     - Token savings via learned patterns (attention_pruning)
  workflow     - Retrieval plans, not context (context_delegation)
  quality      - Error prevention, adds tokens (coherence_verify)
""",
    )
    parser.add_argument("--filter", help="Filter tasks by ID pattern")
    parser.add_argument(
        "--category",
        choices=["compression", "learning", "workflow", "quality"],
        help="Run only tasks in this category",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--tasks", default="track_new_features", help="Task file to use")
    args = parser.parse_args()

    task_file = resolve_task_file(args.tasks)
    tasks = load_tasks(task_file)

    print(f"Loading {len(tasks)} tasks from {task_file}")
    if args.category:
        print(f"Filtering to category: {args.category}")

    data = run_benchmarks(tasks, args.filter, args.category)
    print_results(data, args.json)


if __name__ == "__main__":
    main()
