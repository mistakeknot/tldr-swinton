from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tldr_bench.agent_eval.schema import Condition, TaskCategory, TaskSpec
from tldr_bench.agent_eval.workspace import (
    build_condition_environment,
    capture_patch,
    changed_paths,
    load_replacements,
    materialize_workspace,
    patch_hash,
    run_external_grader,
)


FIXTURE_REPO = Path(__file__).parent / "fixtures" / "agent_eval_repo"


def _make_source_repo(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    shutil.copytree(FIXTURE_REPO, source)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "add", "-A"], cwd=source, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Agent Eval Test",
            "-c",
            "user.email=agent-eval@example.invalid",
            "commit",
            "-qm",
            "fixture source",
        ],
        cwd=source,
        check=True,
    )
    return source


def _make_task_assets(tmp_path: Path, *, old: str = "return 41") -> TaskSpec:
    assets = tmp_path / "external-assets"
    assets.mkdir()
    mutation = assets / "mutation.yaml"
    mutation.write_text(
        "replacements:\n"
        "  - path: app.py\n"
        f"    old: {old!r}\n"
        "    new: 'return 40'\n"
    )
    grader = assets / "grader.py"
    grader.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "text = (Path(sys.argv[1]) / 'app.py').read_text()\n"
        "if 'return 42' in text:\n"
        "    print('EVAL_TESTS passed=2 total=2')\n"
        "    raise SystemExit(0)\n"
        "print('EVAL_TESTS passed=0 total=2')\n"
        "raise SystemExit(1)\n"
    )
    return TaskSpec(
        id="fixture-001",
        title="Repair the answer",
        category=TaskCategory.CROSS_FILE_BUG,
        eligible_for_tldrs=True,
        prompt="Make answer() return the expected value.",
        mutation_path=mutation,
        grader_path=grader,
    )


def _tracked_content(workspace: Path) -> dict[str, bytes]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )
    paths = [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]
    return {
        str(path): (workspace / path).read_bytes()
        for path in paths
        if path.name != "AGENTS.md"
    }


def test_materialized_conditions_share_source_but_isolate_guidance(
    tmp_path: Path,
) -> None:
    source = _make_source_repo(tmp_path)
    task = _make_task_assets(tmp_path)
    baseline = tmp_path / "baseline"
    adaptive = tmp_path / "adaptive"

    materialize_workspace(source, task, Condition.BASELINE, baseline)
    materialize_workspace(source, task, Condition.ADAPTIVE, adaptive)

    assert _tracked_content(baseline) == _tracked_content(adaptive)
    assert "return 40" in (baseline / "app.py").read_text()
    assert "Do not use tldrs" in (baseline / "AGENTS.md").read_text()
    assert "Use tldrs when" in (adaptive / "AGENTS.md").read_text()
    assert not (baseline / "CLAUDE.md").exists()
    assert not (baseline / ".codex").exists()
    assert not (baseline / ".claude-plugin").exists()
    assert not (baseline / "tldr-bench").exists()
    assert (
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=baseline,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "1"
    )
    assert (
        subprocess.run(
            ["git", "status", "--short"],
            cwd=baseline,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        == ""
    )


def test_adaptive_policy_guidance_is_causally_isolated(tmp_path: Path) -> None:
    source = _make_source_repo(tmp_path)
    task = _make_task_assets(tmp_path)
    tool_only = tmp_path / "tool-only"
    one_shot = tmp_path / "one-shot"

    materialize_workspace(
        source,
        task,
        Condition.ADAPTIVE,
        tool_only,
        adaptive_policy="tool_only",
    )
    materialize_workspace(
        source,
        task,
        Condition.ADAPTIVE,
        one_shot,
        adaptive_policy="one_shot",
    )

    tool_only_guidance = (tool_only / "AGENTS.md").read_text()
    one_shot_guidance = (one_shot / "AGENTS.md").read_text()
    assert "tldrs" not in tool_only_guidance.lower()
    normalized_one_shot = " ".join(one_shot_guidance.lower().split())
    assert "at most one tldrs reconnaissance command" in normalized_one_shot
    assert "do not chain tldrs commands" in normalized_one_shot
    assert _tracked_content(tool_only) == _tracked_content(one_shot)


def test_replacements_fail_closed_when_source_drifted(tmp_path: Path) -> None:
    source = _make_source_repo(tmp_path)
    task = _make_task_assets(tmp_path, old="return 999")

    with pytest.raises(ValueError, match="expected exactly one match"):
        materialize_workspace(source, task, Condition.BASELINE, tmp_path / "work")


def test_load_replacements_rejects_path_escape(tmp_path: Path) -> None:
    task = _make_task_assets(tmp_path)
    task.mutation_path.write_text(
        "replacements:\n"
        "  - path: ../outside.py\n"
        "    old: x\n"
        "    new: y\n"
    )

    with pytest.raises(ValueError, match="relative workspace path"):
        load_replacements(task.mutation_path)


def test_condition_environment_removes_or_exposes_tldrs_bin(tmp_path: Path) -> None:
    tldrs_bin = tmp_path / "tldrs-bin"
    other_bin = tmp_path / "other-bin"
    tldrs_bin.mkdir()
    other_bin.mkdir()
    base = {"PATH": os.pathsep.join([str(tldrs_bin), str(other_bin)])}

    baseline = build_condition_environment(
        Condition.BASELINE, base, tldrs_bin_dir=tldrs_bin
    )
    adaptive = build_condition_environment(
        Condition.ADAPTIVE, base, tldrs_bin_dir=tldrs_bin
    )

    assert baseline["PATH"] == str(other_bin)
    assert adaptive["PATH"].split(os.pathsep)[0] == str(tldrs_bin)


def test_external_grader_owns_success_and_patch_hash(tmp_path: Path) -> None:
    source = _make_source_repo(tmp_path)
    task = _make_task_assets(tmp_path)
    workspace = tmp_path / "work"
    clean = tmp_path / "clean"
    materialize_workspace(source, task, Condition.ADAPTIVE, workspace)
    materialize_workspace(source, task, Condition.ADAPTIVE, clean)

    failed = run_external_grader(task, workspace, python_executable=Path(sys.executable))
    (workspace / "app.py").write_text("def answer() -> int:\n    return 42\n")
    passed = run_external_grader(task, workspace, python_executable=Path(sys.executable))

    assert failed.passed is False
    assert failed.exit_code == 1
    assert (failed.tests_passed, failed.tests_total) == (0, 2)
    assert passed.passed is True
    assert (passed.tests_passed, passed.tests_total) == (2, 2)
    assert patch_hash(workspace) != patch_hash(clean)
    assert not task.grader_path.is_relative_to(workspace)


def test_capture_patch_includes_tracked_and_untracked_files(tmp_path: Path) -> None:
    source = _make_source_repo(tmp_path)
    task = _make_task_assets(tmp_path)
    workspace = tmp_path / "work"
    materialize_workspace(source, task, Condition.BASELINE, workspace)
    (workspace / "app.py").write_text("def answer() -> int:\n    return 42\n")
    (workspace / "proof.txt").write_text("external proof\n")

    patch = capture_patch(workspace).decode()

    assert "return 42" in patch
    assert "proof.txt" in patch
    assert "external proof" in patch
    assert changed_paths(workspace) == ("app.py", "proof.txt")
