from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tldr_bench.agent_eval.cli import (
    _resolve_executable,
    _verification_python,
    build_parser,
)


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


def _make_external_eval(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "external-source"
    source.mkdir()
    (source / "app.py").write_text("def answer() -> int:\n    return 41\n")
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "add", "app.py"], cwd=source, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Agent Eval Test",
            "-c",
            "user.email=agent-eval@example.invalid",
            "commit",
            "-qm",
            "external source",
        ],
        cwd=source,
        check=True,
    )

    assets = tmp_path / "external-assets"
    assets.mkdir()
    (assets / "mutation.yaml").write_text(
        "replacements:\n"
        "  - path: app.py\n"
        "    old: 'return 41'\n"
        "    new: 'return 40'\n"
    )
    (assets / "grader.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "text = (Path(sys.argv[1]) / 'app.py').read_text()\n"
        "passed = int('return 42' in text)\n"
        "print(f'EVAL_TESTS passed={passed} total=1')\n"
        "raise SystemExit(0 if passed else 1)\n"
    )
    tasks = assets / "tasks.yaml"
    tasks.write_text(
        "- id: external-001\n"
        "  title: Repair the answer\n"
        "  category: cross_file_bug\n"
        "  eligible_for_tldrs: true\n"
        "  prompt: Make answer return the expected value.\n"
        "  mutation: mutation.yaml\n"
        "  grader: grader.py\n"
    )
    return source, tasks


def _fake_external_codex(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-external-codex"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "workspace = Path(args[args.index('-C') + 1])\n"
        "message = Path(args[args.index('--output-last-message') + 1])\n"
        "target = workspace / 'app.py'\n"
        "target.write_text(target.read_text().replace('return 40', 'return 42'))\n"
        "message.write_text('fixed')\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': 'external'}))\n"
        "print(json.dumps({'type': 'item.completed', 'item': {"
        "'type': 'agent_message', 'text': 'fixed'}}))\n"
        "print(json.dumps({'type': 'turn.completed', 'usage': {"
        "'input_tokens': 50, 'cached_input_tokens': 0, 'output_tokens': 5, "
        "'reasoning_output_tokens': 1}}))\n"
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


def test_verification_python_preserves_virtualenv_entrypoint(tmp_path: Path) -> None:
    real_python = tmp_path / "base-python"
    real_python.write_text("#!/bin/sh\n")
    virtualenv_python = tmp_path / ".venv/bin/python"
    virtualenv_python.parent.mkdir(parents=True)
    virtualenv_python.symlink_to(real_python)

    assert _verification_python(virtualenv_python) == virtualenv_python.absolute()
    assert _verification_python(virtualenv_python) != real_python.resolve()


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
    assert parser.parse_args(
        ["--adaptive-policy", "injected_packet"]
    ).adaptive_policy == "injected_packet"
    assert parser.parse_args(
        ["--adaptive-policy", "injected_runtime"]
    ).adaptive_policy == "injected_runtime"


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


def test_external_source_and_arbitrary_corpus_record_same_sha(tmp_path: Path) -> None:
    source, tasks = _make_external_eval(tmp_path)
    results = tmp_path / "external-results"
    fake_codex = _fake_external_codex(tmp_path)

    listed = _run_cli("--list-tasks", "--tasks-file", str(tasks))
    assert listed.returncode == 0, listed.stderr
    assert "1 tasks" in listed.stdout

    executed = _run_cli(
        "--source-repo",
        str(source),
        "--tasks-file",
        str(tasks),
        "--task",
        "external-001",
        "--conditions",
        "baseline",
        "--repeats",
        "1",
        "--model",
        "test-model",
        "--results-dir",
        str(results),
        "--codex-executable",
        str(fake_codex),
        "--grader-python",
        sys.executable,
    )

    assert executed.returncode == 0, executed.stderr
    metadata = json.loads((results / "metadata.json").read_text())
    source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert metadata["source_repo"] == str(source.resolve())
    assert metadata["source_sha"] == source_sha
    assert len(metadata["evaluator_sha"]) == 40
    outcomes = [
        json.loads(line) for line in (results / "outcomes.jsonl").read_text().splitlines()
    ]
    assert len(outcomes) == 1
    assert outcomes[0]["success"] is True


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


def test_injected_runtime_report_uses_context_owner_gate(tmp_path: Path) -> None:
    results = tmp_path / "gateway-run"
    fake_codex = _fake_codex(tmp_path)
    grader_python = REPO_ROOT / ".venv/bin/python"
    if not grader_python.exists():
        grader_python = Path(sys.executable)

    executed = _run_cli(
        "--task",
        "neg-token-fallback",
        "--conditions",
        "baseline",
        "adaptive",
        "--repeats",
        "1",
        "--adaptive-policy",
        "injected_runtime",
        "--model",
        "test-model",
        "--results-dir",
        str(results),
        "--codex-executable",
        str(fake_codex),
        "--grader-python",
        str(grader_python),
    )

    assert executed.returncode == 0, executed.stderr
    report = json.loads((results / "report.json").read_text())
    gate_names = {gate["name"] for gate in report["gates"]}
    assert "context_owner_recall" in gate_names
    assert "routing_precision" not in gate_names
