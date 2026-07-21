from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from tldr_bench.agent_eval.schema import Condition, TaskCategory
from tldr_bench.agent_eval.tasks import load_agent_tasks
from tldr_bench.agent_eval.workspace import (
    load_replacements,
    materialize_workspace,
    run_external_grader,
)


REPO_ROOT = Path(__file__).parents[2]
TASKS_FILE = REPO_ROOT / "tldr-bench/tldr_bench/tasks/agent_value.yaml"
GRADER_PYTHON = REPO_ROOT / ".venv/bin/python"


def _restore_expected_source(task, workspace: Path) -> None:
    for replacement in load_replacements(task.mutation_path):
        target = workspace / replacement.path
        text = target.read_text()
        assert text.count(replacement.new) == 1, (
            task.id,
            replacement.path,
            "broken mutation is not uniquely reversible",
        )
        target.write_text(text.replace(replacement.new, replacement.old, 1))


def test_agent_value_corpus_has_twelve_balanced_nonleaky_tasks() -> None:
    tasks = load_agent_tasks(TASKS_FILE, require_pilot_corpus=True)

    assert len(tasks) == 12
    assert len({task.id for task in tasks}) == 12
    assert Counter(task.category for task in tasks) == {
        category: 3 for category in TaskCategory
    }
    assert sum(task.eligible_for_tldrs for task in tasks) == 9
    for task in tasks:
        assert task.mutation_path.is_relative_to(REPO_ROOT)
        assert task.grader_path.is_relative_to(REPO_ROOT)
        if task.eligible_for_tldrs:
            assert "src/" not in task.prompt
            assert ".py" not in task.prompt


def test_every_hidden_grader_has_observed_green_red_green_cycle(
    tmp_path: Path,
) -> None:
    tasks = load_agent_tasks(TASKS_FILE, require_pilot_corpus=True)
    python_executable = GRADER_PYTHON if GRADER_PYTHON.exists() else Path(sys.executable)

    for task in tasks:
        original = run_external_grader(
            task, REPO_ROOT, python_executable=python_executable
        )
        assert original.passed, (task.id, "original source", original.stdout, original.stderr)

        workspace = tmp_path / task.id
        materialize_workspace(REPO_ROOT, task, Condition.BASELINE, workspace)
        mutated = run_external_grader(
            task, workspace, python_executable=python_executable
        )
        assert not mutated.passed, (
            task.id,
            "mutation did not break grader",
            mutated.stdout,
            mutated.stderr,
        )

        _restore_expected_source(task, workspace)
        repaired = run_external_grader(
            task, workspace, python_executable=python_executable
        )
        assert repaired.passed, (
            task.id,
            "expected repair did not satisfy grader",
            repaired.stdout,
            repaired.stderr,
        )
