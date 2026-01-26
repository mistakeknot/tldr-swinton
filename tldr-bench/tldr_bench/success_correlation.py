"""Task success rate correlation metrics for tldr-bench.

This module provides tools for tracking and analyzing the correlation between
token savings and task success rates. It enables data-driven validation of
compression strategies by measuring whether reduced context actually helps
agents complete tasks.

Key features:
- Track success/failure outcomes per task variant
- Compute Pearson and Spearman correlations between token savings and success
- Generate confidence intervals for success rate comparisons
- Export results in formats suitable for publication

Usage:
    from tldr_bench.success_correlation import SuccessCorrelator, TaskOutcome

    correlator = SuccessCorrelator()
    correlator.record(TaskOutcome(
        task_id="swe-1234",
        variant="tldrs-context",
        success=True,
        tokens_used=5000,
        baseline_tokens=50000,
    ))
    report = correlator.compute_correlation()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import math
import statistics


@dataclass
class TaskOutcome:
    """Record of a single task execution."""

    task_id: str
    variant: str
    success: bool
    tokens_used: int
    baseline_tokens: int | None = None
    execution_time_ms: int | None = None
    error_category: str | None = None
    patch_correct: bool | None = None
    tests_passed: int | None = None
    tests_total: int | None = None

    @property
    def token_savings(self) -> float:
        """Compute token savings ratio (0.0 to 1.0)."""
        if self.baseline_tokens is None or self.baseline_tokens == 0:
            return 0.0
        return 1.0 - (self.tokens_used / self.baseline_tokens)

    @property
    def compression_ratio(self) -> float:
        """Compute compression ratio (baseline/used)."""
        if self.tokens_used == 0:
            return float("inf")
        if self.baseline_tokens is None:
            return 1.0
        return self.baseline_tokens / self.tokens_used

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "variant": self.variant,
            "success": self.success,
            "tokens_used": self.tokens_used,
            "baseline_tokens": self.baseline_tokens,
            "token_savings": round(self.token_savings, 4),
            "compression_ratio": round(self.compression_ratio, 2),
            "execution_time_ms": self.execution_time_ms,
            "error_category": self.error_category,
            "patch_correct": self.patch_correct,
            "tests_passed": self.tests_passed,
            "tests_total": self.tests_total,
        }


@dataclass
class VariantStats:
    """Aggregated statistics for a variant."""

    variant: str
    total_tasks: int
    successful_tasks: int
    success_rate: float
    avg_tokens: float
    avg_token_savings: float
    median_token_savings: float
    stddev_token_savings: float
    avg_compression_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "success_rate": round(self.success_rate, 4),
            "avg_tokens": round(self.avg_tokens, 1),
            "avg_token_savings": round(self.avg_token_savings, 4),
            "median_token_savings": round(self.median_token_savings, 4),
            "stddev_token_savings": round(self.stddev_token_savings, 4),
            "avg_compression_ratio": round(self.avg_compression_ratio, 2),
        }


@dataclass
class CorrelationReport:
    """Results of correlation analysis."""

    pearson_r: float | None
    pearson_p: float | None
    spearman_rho: float | None
    spearman_p: float | None
    sample_size: int
    success_rate_baseline: float
    success_rate_tldrs: float
    success_rate_delta: float
    confidence_interval_95: tuple[float, float] | None
    variants: list[VariantStats]
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pearson_r": self.pearson_r,
            "pearson_p": self.pearson_p,
            "spearman_rho": self.spearman_rho,
            "spearman_p": self.spearman_p,
            "sample_size": self.sample_size,
            "success_rate_baseline": round(self.success_rate_baseline, 4),
            "success_rate_tldrs": round(self.success_rate_tldrs, 4),
            "success_rate_delta": round(self.success_rate_delta, 4),
            "confidence_interval_95": (
                [round(x, 4) for x in self.confidence_interval_95]
                if self.confidence_interval_95
                else None
            ),
            "variants": [v.to_dict() for v in self.variants],
            "interpretation": self.interpretation,
        }

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            "=== Task Success Rate Correlation Report ===",
            f"Sample size: {self.sample_size} tasks",
            "",
            "Success Rates:",
            f"  Baseline: {self.success_rate_baseline:.1%}",
            f"  TLDRS:    {self.success_rate_tldrs:.1%}",
            f"  Delta:    {self.success_rate_delta:+.1%}",
            "",
        ]

        if self.confidence_interval_95:
            lo, hi = self.confidence_interval_95
            lines.append(f"95% CI for delta: [{lo:+.1%}, {hi:+.1%}]")

        if self.pearson_r is not None:
            lines.append(f"Pearson r (token savings vs success): {self.pearson_r:.3f}")
        if self.spearman_rho is not None:
            lines.append(f"Spearman ρ (rank correlation): {self.spearman_rho:.3f}")

        lines.extend(["", f"Interpretation: {self.interpretation}"])

        return "\n".join(lines)


class SuccessCorrelator:
    """Tracks and analyzes task success rates across variants."""

    def __init__(self) -> None:
        self._outcomes: list[TaskOutcome] = []

    def record(self, outcome: TaskOutcome) -> None:
        """Record a task outcome."""
        self._outcomes.append(outcome)

    def record_batch(self, outcomes: list[TaskOutcome]) -> None:
        """Record multiple task outcomes."""
        self._outcomes.extend(outcomes)

    def load_from_file(self, path: Path) -> int:
        """Load outcomes from a JSONL file. Returns count loaded."""
        count = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                self._outcomes.append(
                    TaskOutcome(
                        task_id=data["task_id"],
                        variant=data["variant"],
                        success=data["success"],
                        tokens_used=data["tokens_used"],
                        baseline_tokens=data.get("baseline_tokens"),
                        execution_time_ms=data.get("execution_time_ms"),
                        error_category=data.get("error_category"),
                        patch_correct=data.get("patch_correct"),
                        tests_passed=data.get("tests_passed"),
                        tests_total=data.get("tests_total"),
                    )
                )
                count += 1
        return count

    def save_to_file(self, path: Path) -> int:
        """Save outcomes to a JSONL file. Returns count saved."""
        with open(path, "w") as f:
            for outcome in self._outcomes:
                f.write(json.dumps(outcome.to_dict()) + "\n")
        return len(self._outcomes)

    def _compute_variant_stats(self, variant: str) -> VariantStats:
        """Compute statistics for a single variant."""
        outcomes = [o for o in self._outcomes if o.variant == variant]
        if not outcomes:
            return VariantStats(
                variant=variant,
                total_tasks=0,
                successful_tasks=0,
                success_rate=0.0,
                avg_tokens=0.0,
                avg_token_savings=0.0,
                median_token_savings=0.0,
                stddev_token_savings=0.0,
                avg_compression_ratio=0.0,
            )

        total = len(outcomes)
        successful = sum(1 for o in outcomes if o.success)
        tokens = [o.tokens_used for o in outcomes]
        savings = [o.token_savings for o in outcomes]
        ratios = [o.compression_ratio for o in outcomes if o.compression_ratio != float("inf")]

        return VariantStats(
            variant=variant,
            total_tasks=total,
            successful_tasks=successful,
            success_rate=successful / total if total else 0.0,
            avg_tokens=statistics.mean(tokens) if tokens else 0.0,
            avg_token_savings=statistics.mean(savings) if savings else 0.0,
            median_token_savings=statistics.median(savings) if savings else 0.0,
            stddev_token_savings=statistics.stdev(savings) if len(savings) > 1 else 0.0,
            avg_compression_ratio=statistics.mean(ratios) if ratios else 0.0,
        )

    def _pearson_correlation(
        self, x: list[float], y: list[float]
    ) -> tuple[float | None, float | None]:
        """Compute Pearson correlation coefficient and p-value."""
        if len(x) < 3 or len(x) != len(y):
            return None, None

        n = len(x)
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)

        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denom_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        denom_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

        if denom_x == 0 or denom_y == 0:
            return None, None

        r = numerator / (denom_x * denom_y)

        # Approximate p-value using t-distribution (requires scipy for exact)
        # For now, use a simple approximation
        t_stat = r * math.sqrt(n - 2) / math.sqrt(1 - r**2) if abs(r) < 1 else float("inf")
        # Rough p-value estimate (not exact without scipy)
        p_approx = 2 * math.exp(-0.5 * t_stat**2) if abs(t_stat) < 10 else 0.0

        return r, p_approx

    def _spearman_correlation(
        self, x: list[float], y: list[float]
    ) -> tuple[float | None, float | None]:
        """Compute Spearman rank correlation coefficient."""
        if len(x) < 3 or len(x) != len(y):
            return None, None

        def rank(values: list[float]) -> list[float]:
            indexed = sorted(enumerate(values), key=lambda t: t[1])
            ranks = [0.0] * len(values)
            for rank_val, (orig_idx, _) in enumerate(indexed, 1):
                ranks[orig_idx] = float(rank_val)
            return ranks

        rank_x = rank(x)
        rank_y = rank(y)
        return self._pearson_correlation(rank_x, rank_y)

    def _confidence_interval(
        self, p1: float, n1: int, p2: float, n2: int
    ) -> tuple[float, float] | None:
        """Compute 95% confidence interval for difference in proportions."""
        if n1 < 2 or n2 < 2:
            return None

        diff = p1 - p2

        # Standard error of difference
        se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)

        # 95% CI using normal approximation
        z = 1.96
        return (diff - z * se, diff + z * se)

    def compute_correlation(self) -> CorrelationReport:
        """Compute correlation report across all recorded outcomes."""
        if not self._outcomes:
            return CorrelationReport(
                pearson_r=None,
                pearson_p=None,
                spearman_rho=None,
                spearman_p=None,
                sample_size=0,
                success_rate_baseline=0.0,
                success_rate_tldrs=0.0,
                success_rate_delta=0.0,
                confidence_interval_95=None,
                variants=[],
                interpretation="No data available.",
            )

        # Identify variants
        variants = sorted(set(o.variant for o in self._outcomes))
        variant_stats = [self._compute_variant_stats(v) for v in variants]

        # Identify baseline (usually "baseline" or "raw")
        baseline_variants = [v for v in variant_stats if "baseline" in v.variant.lower() or "raw" in v.variant.lower()]
        tldrs_variants = [v for v in variant_stats if "tldrs" in v.variant.lower() or "context" in v.variant.lower()]

        baseline_stats = baseline_variants[0] if baseline_variants else None
        tldrs_stats = tldrs_variants[0] if tldrs_variants else variant_stats[-1] if variant_stats else None

        baseline_rate = baseline_stats.success_rate if baseline_stats else 0.0
        tldrs_rate = tldrs_stats.success_rate if tldrs_stats else 0.0
        delta = tldrs_rate - baseline_rate

        # Compute confidence interval
        ci = None
        if baseline_stats and tldrs_stats:
            ci = self._confidence_interval(
                tldrs_rate,
                tldrs_stats.total_tasks,
                baseline_rate,
                baseline_stats.total_tasks,
            )

        # Correlation: token savings vs success (binary 0/1)
        token_savings = [o.token_savings for o in self._outcomes if o.baseline_tokens]
        success_binary = [1.0 if o.success else 0.0 for o in self._outcomes if o.baseline_tokens]

        pearson_r, pearson_p = self._pearson_correlation(token_savings, success_binary)
        spearman_rho, spearman_p = self._spearman_correlation(token_savings, success_binary)

        # Generate interpretation
        interpretation = self._interpret_results(
            delta, ci, pearson_r, len(self._outcomes)
        )

        return CorrelationReport(
            pearson_r=pearson_r,
            pearson_p=pearson_p,
            spearman_rho=spearman_rho,
            spearman_p=spearman_p,
            sample_size=len(self._outcomes),
            success_rate_baseline=baseline_rate,
            success_rate_tldrs=tldrs_rate,
            success_rate_delta=delta,
            confidence_interval_95=ci,
            variants=variant_stats,
            interpretation=interpretation,
        )

    def _interpret_results(
        self,
        delta: float,
        ci: tuple[float, float] | None,
        pearson_r: float | None,
        n: int,
    ) -> str:
        """Generate human-readable interpretation of results."""
        parts = []

        if n < 10:
            parts.append(f"Sample size ({n}) is too small for reliable conclusions.")
        elif n < 50:
            parts.append(f"Sample size ({n}) provides preliminary evidence only.")
        else:
            parts.append(f"Sample size ({n}) is adequate for statistical analysis.")

        if ci:
            lo, hi = ci
            if lo > 0:
                parts.append(f"TLDRS shows significant improvement ({delta:+.1%}, CI excludes zero).")
            elif hi < 0:
                parts.append(f"TLDRS shows significant degradation ({delta:+.1%}, CI excludes zero).")
            else:
                parts.append(f"No significant difference detected ({delta:+.1%}, CI includes zero).")

        if pearson_r is not None:
            if pearson_r > 0.3:
                parts.append("Positive correlation between token savings and success.")
            elif pearson_r < -0.3:
                parts.append("Negative correlation between token savings and success.")
            else:
                parts.append("No strong correlation between token savings and success.")

        return " ".join(parts)

    def export_for_swe_bench(self, output_path: Path) -> dict[str, Any]:
        """Export results in a format compatible with SWE-bench evaluation."""
        by_task: dict[str, dict[str, TaskOutcome]] = {}
        for o in self._outcomes:
            if o.task_id not in by_task:
                by_task[o.task_id] = {}
            by_task[o.task_id][o.variant] = o

        results = []
        for task_id, variants in by_task.items():
            baseline = variants.get("baseline") or variants.get("raw")
            for variant_name, outcome in variants.items():
                results.append(
                    {
                        "instance_id": task_id,
                        "model_name_or_path": f"tldrs-{variant_name}",
                        "resolved": outcome.success,
                        "tokens_used": outcome.tokens_used,
                        "token_savings": outcome.token_savings if baseline else None,
                        "patch_correct": outcome.patch_correct,
                    }
                )

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        return {"exported": len(results), "path": str(output_path)}


def run_swe_bench_correlation_experiment(
    swe_bench_instances: list[dict[str, Any]],
    variants: list[str],
    run_task_fn,  # Callable[[dict, str], TaskOutcome]
) -> CorrelationReport:
    """Run correlation experiment on SWE-bench instances.

    Args:
        swe_bench_instances: List of SWE-bench instance dicts with 'instance_id'
        variants: List of variant names to test (e.g., ['baseline', 'tldrs-context'])
        run_task_fn: Function(instance, variant) -> TaskOutcome

    Returns:
        CorrelationReport with analysis results
    """
    correlator = SuccessCorrelator()

    for instance in swe_bench_instances:
        for variant in variants:
            try:
                outcome = run_task_fn(instance, variant)
                correlator.record(outcome)
            except Exception as e:
                # Record as failure with error
                correlator.record(
                    TaskOutcome(
                        task_id=instance.get("instance_id", "unknown"),
                        variant=variant,
                        success=False,
                        tokens_used=0,
                        error_category=type(e).__name__,
                    )
                )

    return correlator.compute_correlation()
