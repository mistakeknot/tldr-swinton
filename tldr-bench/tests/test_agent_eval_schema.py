from __future__ import annotations

import json
from pathlib import Path

import pytest

from tldr_bench.agent_eval.schema import (
    Condition,
    GradeResult,
    RunOutcome,
    TaskCategory,
    TraceMetrics,
)
from tldr_bench.agent_eval.tasks import load_agent_tasks


def _write_assets(tmp_path: Path) -> tuple[Path, Path]:
    mutation = tmp_path / "mutation.yaml"
    mutation.write_text("replacements: []\n")
    grader = tmp_path / "grader.py"
    grader.write_text("raise SystemExit(0)\n")
    return mutation, grader


def _task_yaml(
    task_id: str,
    category: str,
    mutation: Path,
    grader: Path,
    *,
    eligible: bool,
    prompt: str = "Repair the described behavior.",
    verification_command: str | None = None,
) -> str:
    verification = (
        f"  verification_command: {verification_command!r}\n"
        if verification_command is not None
        else ""
    )
    return f"""
- id: {task_id}
  title: Task {task_id}
  category: {category}
  eligible_for_tldrs: {str(eligible).lower()}
  prompt: {prompt!r}
  mutation: {mutation.name}
  grader: {grader.name}
{verification}"""


def test_load_agent_tasks_builds_strict_typed_specs(tmp_path: Path) -> None:
    mutation, grader = _write_assets(tmp_path)
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text(
        _task_yaml(
            "neg-001",
            "negative_control",
            mutation,
            grader,
            eligible=False,
        )
        + _task_yaml(
            "cross-001",
            "cross_file_bug",
            mutation,
            grader,
            eligible=True,
            verification_command="go test ./...",
        )
        + _task_yaml(
            "diff-001", "diff_regression", mutation, grader, eligible=True
        )
        + _task_yaml(
            "refactor-001",
            "dependency_refactor",
            mutation,
            grader,
            eligible=True,
        )
    )

    tasks = load_agent_tasks(tasks_file)

    assert [task.id for task in tasks] == [
        "neg-001",
        "cross-001",
        "diff-001",
        "refactor-001",
    ]
    assert {task.category for task in tasks} == set(TaskCategory)
    assert tasks[0].eligible_for_tldrs is False
    assert tasks[1].mutation_path == mutation.resolve()
    assert tasks[1].grader_path == grader.resolve()
    assert tasks[1].verification_command == "go test ./..."


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("duplicate", "duplicate task id"),
        ("missing_mutation", "mutation file does not exist"),
        ("missing_grader", "grader file does not exist"),
        ("leaked_mutation", "prompt leaks hidden asset"),
        ("leaked_grader", "prompt leaks hidden asset"),
    ],
)
def test_load_agent_tasks_rejects_invalid_or_leaky_specs(
    tmp_path: Path, change: str, message: str
) -> None:
    mutation, grader = _write_assets(tmp_path)
    prompt = "Repair the described behavior."
    first_mutation = mutation
    first_grader = grader
    second = ""
    if change == "duplicate":
        second = _task_yaml(
            "task-001", "cross_file_bug", mutation, grader, eligible=True
        )
    elif change == "missing_mutation":
        first_mutation = tmp_path / "absent-mutation.yaml"
    elif change == "missing_grader":
        first_grader = tmp_path / "absent-grader.py"
    elif change == "leaked_mutation":
        prompt = f"Read {mutation.name} and repair the behavior."
    elif change == "leaked_grader":
        prompt = f"Use {grader.name} to repair the behavior."

    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text(
        _task_yaml(
            "task-001",
            "cross_file_bug",
            first_mutation,
            first_grader,
            eligible=True,
            prompt=prompt,
        )
        + second
    )

    with pytest.raises(ValueError, match=message):
        load_agent_tasks(tasks_file)


def test_negative_controls_must_be_ineligible(tmp_path: Path) -> None:
    mutation, grader = _write_assets(tmp_path)
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text(
        _task_yaml(
            "neg-001", "negative_control", mutation, grader, eligible=True
        )
    )

    with pytest.raises(ValueError, match="negative controls must be ineligible"):
        load_agent_tasks(tasks_file)


def test_pilot_mode_requires_twelve_balanced_tasks(tmp_path: Path) -> None:
    mutation, grader = _write_assets(tmp_path)
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text(
        _task_yaml(
            "neg-001", "negative_control", mutation, grader, eligible=False
        )
    )

    with pytest.raises(ValueError, match="pilot corpus requires exactly 12 tasks"):
        load_agent_tasks(tasks_file, require_pilot_corpus=True)


def test_run_outcome_round_trips_as_json_primitives() -> None:
    outcome = RunOutcome(
        task_id="cross-001",
        condition=Condition.ADAPTIVE,
        repeat=2,
        agent_exit_code=0,
        agent_timed_out=False,
        elapsed_ms=4321,
        patch_hash="abc123",
        trace=TraceMetrics(
            model="gpt-current",
            input_tokens=1200,
            cached_input_tokens=100,
            output_tokens=300,
            total_tokens=1500,
            tool_calls=5,
            tldrs_calls=1,
            raw_read_calls=2,
            raw_read_paths=("src/owner.py", "src/owner.py"),
            unique_raw_read_paths=("src/owner.py",),
            duplicate_raw_read_paths=1,
            compactions=0,
            commands=("tldrs context target --project .", "sed -n 1,80p file.py"),
            errors=(),
        ),
        grade=GradeResult(
            passed=True,
            exit_code=0,
            tests_passed=3,
            tests_total=3,
            stdout="3 passed",
            stderr="",
        ),
        contaminated=False,
        contamination_reasons=(),
        owner_paths=("src/owner.py",),
        changed_paths=("src/owner.py", "src/helper.py"),
        owner_read_precision=1.0,
        owner_read_recall=1.0,
        owner_change_precision=0.5,
        owner_change_recall=1.0,
    )

    encoded = json.dumps(outcome.to_dict())
    restored = RunOutcome.from_dict(json.loads(encoded))

    assert restored == outcome
    assert restored.cell_id == "cross-001__adaptive__r02"
    assert restored.success is True
