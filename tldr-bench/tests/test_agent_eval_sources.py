from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from tldr_bench.agent_eval.sources import load_source_specs, prepare_sources
from tldr_bench.agent_eval.schema import Condition
from tldr_bench.agent_eval.tasks import load_agent_tasks
from tldr_bench.agent_eval.workspace import (
    load_replacements,
    materialize_workspace,
    run_external_grader,
)


def _make_origin(tmp_path: Path) -> tuple[Path, str]:
    origin = tmp_path / "origin"
    origin.mkdir()
    (origin / "main.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=origin, check=True)
    subprocess.run(["git", "add", "main.py"], cwd=origin, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Source Test",
            "-c",
            "user.email=source@example.invalid",
            "commit",
            "-qm",
            "source",
        ],
        cwd=origin,
        check=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=origin,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    return origin, sha


def test_prepare_sources_checks_out_clean_detached_pinned_sha(tmp_path: Path) -> None:
    origin, sha = _make_origin(tmp_path)
    manifest = tmp_path / "sources.yaml"
    manifest.write_text(
        "sources:\n"
        "  - id: fixture-python\n"
        f"    repository: {origin.as_uri()}\n"
        f"    revision: {sha}\n"
        "    language: python\n"
        "    license: BSD-3-Clause\n"
    )

    specs = load_source_specs(manifest)
    prepared = prepare_sources(specs, tmp_path / "prepared")

    checkout = prepared["fixture-python"]
    assert checkout == (tmp_path / "prepared/fixture-python").resolve()
    assert (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        == sha
    )
    assert (
        subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"],
            cwd=checkout,
            check=False,
        ).returncode
        != 0
    )

    (checkout / "main.py").write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="source checkout is dirty"):
        prepare_sources(specs, tmp_path / "prepared")


def test_external_task_manifests_are_valid_and_do_not_leak_hidden_assets() -> None:
    root = Path(__file__).parents[2] / "tldr-bench/agent_eval/external"

    python_tasks = load_agent_tasks(root / "python/tasks.yaml")
    go_tasks = load_agent_tasks(root / "go/tasks.yaml")

    assert [task.id for task in python_tasks] == [
        "itsdangerous-base64-padding",
        "itsdangerous-key-rotation",
    ]
    assert [task.id for task in go_tasks] == [
        "go-cmp-equate-empty",
        "go-cmp-equate-approx",
    ]
    assert all(task.eligible_for_tldrs for task in python_tasks + go_tasks)


@pytest.mark.parametrize(
    ("source_id", "corpus", "task_id"),
    [
        ("itsdangerous-python", "python", "itsdangerous-base64-padding"),
        ("itsdangerous-python", "python", "itsdangerous-key-rotation"),
        ("go-cmp", "go", "go-cmp-equate-empty"),
        ("go-cmp", "go", "go-cmp-equate-approx"),
    ],
)
def test_external_mutation_fails_and_reference_repair_passes(
    tmp_path: Path, source_id: str, corpus: str, task_id: str
) -> None:
    repo = Path(__file__).parents[2]
    source = repo / "tldr-bench/.agent-eval-sources" / source_id
    if not (source / ".git").exists():
        pytest.skip("external evaluation sources are opt-in")
    tasks = load_agent_tasks(
        repo / "tldr-bench/agent_eval/external" / corpus / "tasks.yaml"
    )
    task = next(task for task in tasks if task.id == task_id)
    workspace = tmp_path / task_id
    materialize_workspace(source, task, Condition.BASELINE, workspace)

    failed = run_external_grader(
        task, workspace, python_executable=Path(sys.executable)
    )
    assert failed.passed is False, failed.stdout + failed.stderr

    for replacement in load_replacements(task.mutation_path):
        target = workspace / replacement.path
        text = target.read_text()
        assert text.count(replacement.new) == 1
        target.write_text(text.replace(replacement.new, replacement.old, 1))

    passed = run_external_grader(
        task, workspace, python_executable=Path(sys.executable)
    )
    assert passed.passed is True, passed.stdout + passed.stderr
