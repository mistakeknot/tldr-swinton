from __future__ import annotations

import json
from pathlib import Path

import pytest

from tldr_bench.agent_eval.analysis import (
    GateStatus,
    analyze_outcomes,
    bootstrap_median_interval,
)
from tldr_bench.agent_eval.report import render_markdown
from tldr_bench.agent_eval.schema import (
    Condition,
    GradeResult,
    RunOutcome,
    TaskCategory,
    TaskSpec,
    TraceMetrics,
)


def _task(task_id: str, category: TaskCategory, eligible: bool) -> TaskSpec:
    return TaskSpec(
        id=task_id,
        title=task_id,
        category=category,
        eligible_for_tldrs=eligible,
        prompt="Repair the behavior.",
        mutation_path=Path("mutation.yaml"),
        grader_path=Path("grader.py"),
    )


def _outcome(
    task_id: str,
    condition: Condition,
    *,
    success: bool = True,
    total_tokens: int | None = 100,
    cached_tokens: int = 0,
    elapsed_ms: int = 1000,
    tldrs_calls: int = 0,
    repeat: int = 1,
    contaminated: bool = False,
) -> RunOutcome:
    return RunOutcome(
        task_id=task_id,
        condition=condition,
        repeat=repeat,
        agent_exit_code=0,
        agent_timed_out=False,
        elapsed_ms=elapsed_ms,
        patch_hash=f"{task_id}-{condition.value}-{repeat}",
        trace=TraceMetrics(
            model="gpt-eval",
            input_tokens=total_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=0 if total_tokens is not None else None,
            total_tokens=total_tokens,
            tool_calls=1,
            tldrs_calls=tldrs_calls,
        ),
        grade=GradeResult(passed=success, exit_code=0 if success else 1),
        contaminated=contaminated,
    )


def test_paired_analysis_passes_all_agreed_gates() -> None:
    tasks = [
        _task("eligible-a", TaskCategory.CROSS_FILE_BUG, True),
        _task("eligible-b", TaskCategory.DIFF_REGRESSION, True),
        _task("negative-a", TaskCategory.NEGATIVE_CONTROL, False),
    ]
    outcomes = [
        _outcome("eligible-a", Condition.BASELINE, total_tokens=100),
        _outcome(
            "eligible-a",
            Condition.ADAPTIVE,
            total_tokens=70,
            elapsed_ms=1080,
            tldrs_calls=1,
        ),
        _outcome("eligible-b", Condition.BASELINE, total_tokens=100),
        _outcome(
            "eligible-b",
            Condition.ADAPTIVE,
            total_tokens=60,
            elapsed_ms=1080,
            tldrs_calls=1,
        ),
        _outcome("negative-a", Condition.BASELINE, total_tokens=100),
        _outcome(
            "negative-a",
            Condition.ADAPTIVE,
            total_tokens=104,
            elapsed_ms=1080,
        ),
    ]

    analysis = analyze_outcomes(tasks, outcomes, expected_repeats=1)

    assert analysis.verdict is GateStatus.PASS
    assert analysis.metrics.baseline_successes == 3
    assert analysis.metrics.adaptive_successes == 3
    assert analysis.metrics.net_additional_failures == 0
    assert analysis.metrics.eligible_token_savings_median == pytest.approx(0.35)
    assert analysis.metrics.negative_control_overhead_median == pytest.approx(0.04)
    assert analysis.metrics.latency_regression_median == pytest.approx(0.08)
    assert analysis.metrics.routing_precision == 1.0
    assert analysis.metrics.routing_recall == 1.0
    assert all(gate.status is GateStatus.PASS for gate in analysis.gates)


def test_paired_analysis_fails_without_moving_thresholds() -> None:
    tasks = [
        _task("eligible-a", TaskCategory.CROSS_FILE_BUG, True),
        _task("eligible-b", TaskCategory.DIFF_REGRESSION, True),
        _task("negative-a", TaskCategory.NEGATIVE_CONTROL, False),
    ]
    outcomes: list[RunOutcome] = []
    for task in tasks:
        outcomes.append(_outcome(task.id, Condition.BASELINE, success=True))
        outcomes.append(
            _outcome(
                task.id,
                Condition.ADAPTIVE,
                success=task.id == "negative-a",
                total_tokens=110,
                elapsed_ms=1200,
                tldrs_calls=1 if task.id == "negative-a" else 0,
            )
        )

    analysis = analyze_outcomes(tasks, outcomes, expected_repeats=1)

    assert analysis.verdict is GateStatus.FAIL
    assert analysis.metrics.net_additional_failures == 2
    assert analysis.gate("correctness_non_inferiority").status is GateStatus.FAIL
    assert analysis.gate("eligible_token_savings").status is GateStatus.FAIL
    assert analysis.gate("negative_control_overhead").status is GateStatus.FAIL
    assert analysis.gate("latency_regression").status is GateStatus.FAIL
    assert analysis.gate("routing_precision").status is GateStatus.FAIL


def test_missing_or_contaminated_cells_make_verdict_inconclusive() -> None:
    tasks = [_task("eligible-a", TaskCategory.CROSS_FILE_BUG, True)]

    missing = analyze_outcomes(
        tasks,
        [_outcome("eligible-a", Condition.BASELINE)],
        expected_repeats=1,
    )
    contaminated = analyze_outcomes(
        tasks,
        [
            _outcome("eligible-a", Condition.BASELINE, tldrs_calls=1),
            _outcome(
                "eligible-a", Condition.ADAPTIVE, total_tokens=70, tldrs_calls=1
            ),
        ],
        expected_repeats=1,
    )

    assert missing.verdict is GateStatus.INCONCLUSIVE
    assert missing.incomplete_cells == ("eligible-a__adaptive__r01",)
    assert contaminated.verdict is GateStatus.INCONCLUSIVE
    assert "eligible-a__baseline__r01 called tldrs" in contaminated.contamination


def test_missing_native_usage_makes_token_gate_inconclusive() -> None:
    tasks = [_task("eligible-a", TaskCategory.CROSS_FILE_BUG, True)]
    outcomes = [
        _outcome("eligible-a", Condition.BASELINE, total_tokens=None),
        _outcome(
            "eligible-a",
            Condition.ADAPTIVE,
            total_tokens=None,
            tldrs_calls=1,
        ),
    ]

    analysis = analyze_outcomes(tasks, outcomes, expected_repeats=1)

    assert analysis.verdict is GateStatus.INCONCLUSIVE
    assert analysis.gate("eligible_token_savings").status is GateStatus.INCONCLUSIVE


def test_report_keeps_raw_paired_cells_and_gate_evidence() -> None:
    tasks = [
        _task("eligible-a", TaskCategory.CROSS_FILE_BUG, True),
        _task("negative-a", TaskCategory.NEGATIVE_CONTROL, False),
    ]
    outcomes = [
        _outcome("eligible-a", Condition.BASELINE),
        _outcome(
            "eligible-a", Condition.ADAPTIVE, total_tokens=70, tldrs_calls=1
        ),
        _outcome("negative-a", Condition.BASELINE),
        _outcome("negative-a", Condition.ADAPTIVE, total_tokens=104),
    ]

    analysis = analyze_outcomes(tasks, outcomes, expected_repeats=1)
    payload = json.loads(json.dumps(analysis.to_dict()))
    markdown = render_markdown(analysis)

    assert payload["verdict"] == "pass"
    assert payload["pairs"][0]["baseline"]["cell_id"].endswith("r01")
    assert "| correctness_non_inferiority | PASS |" in markdown
    assert "eligible-a__baseline__r01" in markdown


def test_bootstrap_interval_is_deterministic_and_ordered() -> None:
    first = bootstrap_median_interval([0.1, 0.2, 0.3, 0.4], samples=200, seed=7)
    second = bootstrap_median_interval([0.1, 0.2, 0.3, 0.4], samples=200, seed=7)

    assert first == second
    assert first is not None
    assert first[0] <= 0.25 <= first[1]
