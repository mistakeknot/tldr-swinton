from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tldr_bench.agent_eval.cli import _resolve_executable, build_parser


REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "tldr-bench/scripts/run_agent_value_eval.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "tldr-bench")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _fake_codex(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "workspace = Path(args[args.index('-C') + 1])\n"
        "message = Path(args[args.index('--output-last-message') + 1])\n"
        "target = workspace / 'src/tldr_swinton/modules/core/token_utils.py'\n"
        "target.write_text(target.read_text().replace('len(text) // 8', 'len(text) // 4'))\n"
        "message.write_text('fixed')\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': 'fake-thread'}))\n"
        "print(json.dumps({'type': 'turn.started'}))\n"
        "print(json.dumps({'type': 'item.completed', 'item': {"
        "'type': 'command_execution', 'command': 'pwd', 'aggregated_output': str(workspace), "
        "'exit_code': 0, 'status': 'completed'}}))\n"
        "print(json.dumps({'type': 'item.completed', 'item': {"
        "'type': 'agent_message', 'text': 'fixed'}}))\n"
        "tokens = 90 if os.environ['TLDRS_EVAL_CONDITION'] == 'adaptive' else 100\n"
        "print(json.dumps({'type': 'turn.completed', 'usage': {"
        "'input_tokens': tokens, 'cached_input_tokens': 0, 'output_tokens': 10, "
        "'reasoning_output_tokens': 2}}))\n"
    )
    executable.chmod(0o755)
    return executable


def test_resolve_executable_before_condition_path_is_sanitized(
    tmp_path: Path, monkeypatch
) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert _resolve_executable(Path("codex")) == executable.resolve()


def test_default_model_uses_codex_supported_concrete_id(monkeypatch) -> None:
    monkeypatch.delenv("TLDRS_EVAL_MODEL", raising=False)

    args = build_parser().parse_args([])
    assert args.model == "gpt-5.6-sol"
    assert args.adaptive_policy == "current"


def test_adaptive_policy_accepts_isolated_experiment_arms() -> None:
    parser = build_parser()

    assert parser.parse_args(["--adaptive-policy", "tool_only"]).adaptive_policy == (
        "tool_only"
    )
    assert parser.parse_args(["--adaptive-policy", "one_shot"]).adaptive_policy == (
        "one_shot"
    )


def test_list_tasks_and_dry_run_render_stable_cells(tmp_path: Path) -> None:
    listed = _run_cli("--list-tasks")
    assert listed.returncode == 0, listed.stderr
    assert "12 tasks" in listed.stdout
    assert "negative_control" in listed.stdout

    dry = _run_cli(
        "--smoke",
        "--dry-run",
        "--model",
        "test-model",
        "--results-dir",
        str(tmp_path / "dry"),
    )
    assert dry.returncode == 0, dry.stderr
    assert "4 cells" in dry.stdout
    assert "neg-token-fallback__baseline__r01" in dry.stdout
    assert "cross-gitignore-nested__adaptive__r01" in dry.stdout
    assert "codex exec" in dry.stdout
    assert not (tmp_path / "dry").exists()


def test_execute_resume_and_report_only(tmp_path: Path) -> None:
    results = tmp_path / "run"
    fake_codex = _fake_codex(tmp_path)
    grader_python = REPO_ROOT / ".venv/bin/python"
    if not grader_python.exists():
        grader_python = Path(sys.executable)
    common = (
        "--task",
        "neg-token-fallback",
        "--conditions",
        "baseline",
        "adaptive",
        "--repeats",
        "1",
        "--model",
        "test-model",
        "--results-dir",
        str(results),
        "--codex-executable",
        str(fake_codex),
        "--grader-python",
        str(grader_python),
    )

    executed = _run_cli(*common)
    assert executed.returncode == 0, executed.stderr
    outcomes_path = results / "outcomes.jsonl"
    outcomes = [json.loads(line) for line in outcomes_path.read_text().splitlines()]
    assert len(outcomes) == 2
    assert all(outcome["success"] for outcome in outcomes)
    assert {outcome["condition"] for outcome in outcomes} == {"baseline", "adaptive"}
    assert all(
        outcome["owner_paths"]
        == ["src/tldr_swinton/modules/core/token_utils.py"]
        for outcome in outcomes
    )
    assert all(outcome["owner_change_precision"] == 1.0 for outcome in outcomes)
    assert all(outcome["owner_change_recall"] == 1.0 for outcome in outcomes)
    for outcome in outcomes:
        cell = outcome["cell_id"]
        assert (results / "traces" / f"{cell}.jsonl").is_file()
        assert (results / "patches" / f"{cell}.diff").is_file()
        assert (results / "graders" / f"{cell}.stdout").is_file()
    assert (results / "metadata.json").is_file()
    metadata = json.loads((results / "metadata.json").read_text())
    assert metadata["seed"] == 42
    assert metadata["adaptive_policy"] == "current"
    assert len(metadata["task_corpus_sha256"]) == 64
    assert (results / "report.json").is_file()
    assert (results / "report.md").is_file()

    resumed = _run_cli(*common, "--resume")
    assert resumed.returncode == 0, resumed.stderr
    assert "skipped 2 completed cells" in resumed.stdout
    assert len(outcomes_path.read_text().splitlines()) == 2

    policy_mismatch = _run_cli(
        *common,
        "--resume",
        "--adaptive-policy",
        "one_shot",
    )
    assert policy_mismatch.returncode == 2
    assert "resume configuration mismatch: adaptive_policy" in policy_mismatch.stderr

    reported = _run_cli(
        "--report-only",
        "--results-dir",
        str(results),
    )
    assert reported.returncode == 0, reported.stderr
    report = json.loads((results / "report.json").read_text())
    assert f"Verdict: {report['verdict'].upper()}" in reported.stdout
