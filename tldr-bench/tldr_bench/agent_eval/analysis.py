from __future__ import annotations

import random
import statistics
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from .schema import Condition, GateThresholds, RunOutcome, TaskSpec


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class PairedCell:
    task_id: str
    repeat: int
    eligible_for_tldrs: bool
    baseline: RunOutcome
    adaptive: RunOutcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "repeat": self.repeat,
            "eligible_for_tldrs": self.eligible_for_tldrs,
            "baseline": self.baseline.to_dict(),
            "adaptive": self.adaptive.to_dict(),
        }


@dataclass(frozen=True)
class PairedMetrics:
    pair_count: int
    baseline_successes: int
    adaptive_successes: int
    lost_successes: int
    gained_successes: int
    net_additional_failures: int
    eligible_token_savings_median: float | None
    eligible_token_savings_ci95: tuple[float, float] | None
    negative_control_overhead_median: float | None
    negative_control_overhead_ci95: tuple[float, float] | None
    latency_regression_median: float | None
    latency_regression_ci95: tuple[float, float] | None
    routing_precision: float | None
    routing_recall: float | None
    routing_true_positives: int
    routing_false_positives: int


@dataclass(frozen=True)
class GateResult:
    name: str
    status: GateStatus
    observed: float | int | None
    threshold: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class EvaluationAnalysis:
    verdict: GateStatus
    metrics: PairedMetrics
    gates: tuple[GateResult, ...]
    pairs: tuple[PairedCell, ...]
    incomplete_cells: tuple[str, ...]
    contamination: tuple[str, ...]
    thresholds: GateThresholds

    def gate(self, name: str) -> GateResult:
        for gate in self.gates:
            if gate.name == name:
                return gate
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        metrics = asdict(self.metrics)
        return {
            "verdict": self.verdict.value,
            "metrics": metrics,
            "gates": [gate.to_dict() for gate in self.gates],
            "pairs": [pair.to_dict() for pair in self.pairs],
            "incomplete_cells": list(self.incomplete_cells),
            "contamination": list(self.contamination),
            "thresholds": asdict(self.thresholds),
        }


def bootstrap_median_interval(
    values: list[float], *, samples: int = 2000, seed: int = 42
) -> tuple[float, float] | None:
    if not values:
        return None
    if samples <= 0:
        raise ValueError("bootstrap samples must be positive")
    rng = random.Random(seed)
    size = len(values)
    medians = sorted(
        statistics.median(rng.choice(values) for _ in range(size))
        for _ in range(samples)
    )
    lower_index = max(0, int(samples * 0.025) - 1)
    upper_index = min(samples - 1, int(samples * 0.975))
    return (medians[lower_index], medians[upper_index])


def _gate(
    name: str,
    observed: float | int | None,
    *,
    threshold: str,
    passes: bool | None,
    detail: str,
) -> GateResult:
    if passes is None:
        status = GateStatus.INCONCLUSIVE
    else:
        status = GateStatus.PASS if passes else GateStatus.FAIL
    return GateResult(name, status, observed, threshold, detail)


def _cell_id(task_id: str, condition: Condition, repeat: int) -> str:
    return f"{task_id}__{condition.value}__r{repeat:02d}"


def analyze_outcomes(
    tasks: list[TaskSpec],
    outcomes: list[RunOutcome],
    *,
    expected_repeats: int,
    thresholds: GateThresholds | None = None,
    bootstrap_samples: int = 2000,
    seed: int = 42,
) -> EvaluationAnalysis:
    if expected_repeats <= 0:
        raise ValueError("expected_repeats must be positive")
    active_thresholds = thresholds or GateThresholds()
    task_by_id = {task.id: task for task in tasks}
    if len(task_by_id) != len(tasks):
        raise ValueError("task ids must be unique")

    outcome_by_cell: dict[tuple[str, Condition, int], RunOutcome] = {}
    for outcome in outcomes:
        if outcome.task_id not in task_by_id:
            raise ValueError(f"outcome references unknown task: {outcome.task_id}")
        key = (outcome.task_id, outcome.condition, outcome.repeat)
        if key in outcome_by_cell:
            raise ValueError(f"duplicate outcome cell: {outcome.cell_id}")
        outcome_by_cell[key] = outcome

    incomplete: list[str] = []
    pairs: list[PairedCell] = []
    for task in tasks:
        for repeat in range(1, expected_repeats + 1):
            baseline = outcome_by_cell.get((task.id, Condition.BASELINE, repeat))
            adaptive = outcome_by_cell.get((task.id, Condition.ADAPTIVE, repeat))
            if baseline is None:
                incomplete.append(_cell_id(task.id, Condition.BASELINE, repeat))
            if adaptive is None:
                incomplete.append(_cell_id(task.id, Condition.ADAPTIVE, repeat))
            if baseline is not None and adaptive is not None:
                pairs.append(
                    PairedCell(
                        task_id=task.id,
                        repeat=repeat,
                        eligible_for_tldrs=task.eligible_for_tldrs,
                        baseline=baseline,
                        adaptive=adaptive,
                    )
                )

    contamination: list[str] = []
    for outcome in outcomes:
        if outcome.contaminated:
            reasons = ", ".join(outcome.contamination_reasons) or "flagged"
            contamination.append(f"{outcome.cell_id} contaminated: {reasons}")
        if (
            outcome.condition is Condition.BASELINE
            and outcome.trace.tldrs_calls > 0
        ):
            contamination.append(f"{outcome.cell_id} called tldrs")

    baseline_successes = sum(pair.baseline.success for pair in pairs)
    adaptive_successes = sum(pair.adaptive.success for pair in pairs)
    lost_successes = sum(
        pair.baseline.success and not pair.adaptive.success for pair in pairs
    )
    gained_successes = sum(
        pair.adaptive.success and not pair.baseline.success for pair in pairs
    )
    net_additional_failures = max(0, baseline_successes - adaptive_successes)

    eligible_savings: list[float] = []
    negative_overhead: list[float] = []
    latency_regression: list[float] = []
    routing_true_positives = 0
    routing_false_positives = 0
    eligible_cells = 0
    for pair in pairs:
        baseline_tokens = pair.baseline.trace.uncached_total_tokens
        adaptive_tokens = pair.adaptive.trace.uncached_total_tokens
        if baseline_tokens is not None and baseline_tokens > 0 and adaptive_tokens is not None:
            delta = (adaptive_tokens - baseline_tokens) / baseline_tokens
            if pair.eligible_for_tldrs:
                eligible_savings.append(-delta)
            else:
                negative_overhead.append(delta)
        if pair.baseline.elapsed_ms > 0:
            latency_regression.append(
                (pair.adaptive.elapsed_ms - pair.baseline.elapsed_ms)
                / pair.baseline.elapsed_ms
            )
        adaptive_used_tldrs = pair.adaptive.trace.tldrs_calls > 0
        if pair.eligible_for_tldrs:
            eligible_cells += 1
            if adaptive_used_tldrs:
                routing_true_positives += 1
        elif adaptive_used_tldrs:
            routing_false_positives += 1

    routing_calls = routing_true_positives + routing_false_positives
    routing_precision = (
        routing_true_positives / routing_calls if routing_calls else 0.0
    )
    routing_recall = (
        routing_true_positives / eligible_cells if eligible_cells else None
    )
    metrics = PairedMetrics(
        pair_count=len(pairs),
        baseline_successes=baseline_successes,
        adaptive_successes=adaptive_successes,
        lost_successes=lost_successes,
        gained_successes=gained_successes,
        net_additional_failures=net_additional_failures,
        eligible_token_savings_median=(
            statistics.median(eligible_savings) if eligible_savings else None
        ),
        eligible_token_savings_ci95=bootstrap_median_interval(
            eligible_savings, samples=bootstrap_samples, seed=seed
        ),
        negative_control_overhead_median=(
            statistics.median(negative_overhead) if negative_overhead else None
        ),
        negative_control_overhead_ci95=bootstrap_median_interval(
            negative_overhead, samples=bootstrap_samples, seed=seed + 1
        ),
        latency_regression_median=(
            statistics.median(latency_regression) if latency_regression else None
        ),
        latency_regression_ci95=bootstrap_median_interval(
            latency_regression, samples=bootstrap_samples, seed=seed + 2
        ),
        routing_precision=routing_precision,
        routing_recall=routing_recall,
        routing_true_positives=routing_true_positives,
        routing_false_positives=routing_false_positives,
    )

    gates = (
        _gate(
            "correctness_non_inferiority",
            net_additional_failures,
            threshold=f"<= {active_thresholds.max_additional_failures} additional failures",
            passes=(
                net_additional_failures
                <= active_thresholds.max_additional_failures
            )
            if pairs
            else None,
            detail=f"lost={lost_successes}, gained={gained_successes}",
        ),
        _gate(
            "eligible_token_savings",
            metrics.eligible_token_savings_median,
            threshold=f">= {active_thresholds.min_eligible_token_savings:.0%}",
            passes=(
                metrics.eligible_token_savings_median
                >= active_thresholds.min_eligible_token_savings
            )
            if metrics.eligible_token_savings_median is not None
            else None,
            detail=f"n={len(eligible_savings)} paired eligible cells",
        ),
        _gate(
            "negative_control_overhead",
            metrics.negative_control_overhead_median,
            threshold=f"<= {active_thresholds.max_negative_control_overhead:.0%}",
            passes=(
                metrics.negative_control_overhead_median
                <= active_thresholds.max_negative_control_overhead
            )
            if metrics.negative_control_overhead_median is not None
            else None,
            detail=f"n={len(negative_overhead)} paired negative controls",
        ),
        _gate(
            "latency_regression",
            metrics.latency_regression_median,
            threshold=f"<= {active_thresholds.max_latency_regression:.0%}",
            passes=(
                metrics.latency_regression_median
                <= active_thresholds.max_latency_regression
            )
            if metrics.latency_regression_median is not None
            else None,
            detail=f"n={len(latency_regression)} paired cells",
        ),
        _gate(
            "routing_precision",
            routing_precision if eligible_cells else None,
            threshold=f">= {active_thresholds.min_routing_precision:.0%}",
            passes=(
                routing_precision >= active_thresholds.min_routing_precision
            )
            if eligible_cells
            else None,
            detail=(
                f"true_positives={routing_true_positives}, "
                f"false_positives={routing_false_positives}, recall={routing_recall}"
            ),
        ),
    )

    if incomplete or contamination:
        verdict = GateStatus.INCONCLUSIVE
    elif any(gate.status is GateStatus.FAIL for gate in gates):
        verdict = GateStatus.FAIL
    elif all(gate.status is GateStatus.PASS for gate in gates):
        verdict = GateStatus.PASS
    else:
        verdict = GateStatus.INCONCLUSIVE

    return EvaluationAnalysis(
        verdict=verdict,
        metrics=metrics,
        gates=gates,
        pairs=tuple(pairs),
        incomplete_cells=tuple(incomplete),
        contamination=tuple(contamination),
        thresholds=active_thresholds,
    )
