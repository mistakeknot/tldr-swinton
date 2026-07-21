from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

from tldr_bench.agent_eval.codex_runner import (
    CodexRunConfig,
    build_codex_command,
    parse_codex_trace,
    run_codex,
)
from tldr_bench.agent_eval.schema import Condition
from tldr_bench.agent_eval.workspace import build_condition_environment


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_current_codex_jsonl_trace() -> None:
    parsed = parse_codex_trace(
        (FIXTURES / "codex_trace_success.jsonl").read_text(),
        requested_model="gpt-eval",
    )

    assert parsed.metrics.model == "gpt-eval"
    assert parsed.metrics.input_tokens == 1200
    assert parsed.metrics.cached_input_tokens == 400
    assert parsed.metrics.output_tokens == 300
    assert parsed.metrics.reasoning_output_tokens == 20
    assert parsed.metrics.total_tokens == 1500
    assert parsed.metrics.tool_calls == 2
    assert parsed.metrics.tool_output_bytes == 31
    assert parsed.metrics.tldrs_calls == 1
    assert parsed.metrics.raw_read_calls == 1
    assert parsed.metrics.compactions == 1
    assert parsed.final_message == "Implemented and verified."
    assert parsed.thread_id == "thread-123"
    assert len(parsed.metrics.commands) == 2
    assert parsed.metrics.errors == ()


def test_parse_trace_preserves_errors_and_malformed_lines() -> None:
    parsed = parse_codex_trace(
        (FIXTURES / "codex_trace_failure.jsonl").read_text(),
        requested_model="gpt-eval",
    )

    assert parsed.metrics.tool_calls == 1
    assert parsed.metrics.raw_read_calls == 1
    assert parsed.metrics.tldrs_calls == 0
    assert parsed.metrics.errors == (
        "non-json trace line: Reading additional input from stdin...",
        "non-json trace line: not-json",
        "model request failed",
        "command failed (1): /bin/zsh -lc 'cat src/target.py'",
    )


def test_build_codex_command_fixes_harness_controls(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "last-message.txt"
    config = CodexRunConfig(
        model="gpt-eval",
        reasoning_effort="medium",
        timeout_s=60,
        codex_executable=Path("/opt/tools/codex"),
    )

    command = build_codex_command(
        config,
        workspace=workspace,
        prompt="Repair the bug.",
        output_last_message=output,
    )

    assert command[0] == "/opt/tools/codex"
    assert command[1] == "exec"
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--strict-config" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert command[command.index("--model") + 1] == "gpt-eval"
    assert command[command.index("-C") + 1] == str(workspace.resolve())
    assert command[command.index("--output-last-message") + 1] == str(
        output.resolve()
    )
    assert 'approval_policy="never"' in command
    assert 'model_reasoning_effort="medium"' in command
    assert command[-1] == "Repair the bug."


def _write_fake_codex(path: Path) -> None:
    path.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, pathlib, sys, time\n"
        "args = sys.argv[1:]\n"
        "prompt = args[-1]\n"
        "if prompt == 'timeout':\n"
        "    time.sleep(5)\n"
        "output = pathlib.Path(args[args.index('--output-last-message') + 1])\n"
        "output.write_text('fake final')\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': 'fake-thread'}))\n"
        "command = 'condition=' + os.environ.get('TLDRS_EVAL_CONDITION', 'missing')\n"
        "print(json.dumps({'type': 'item.completed', 'item': {'id': 'i0', 'type': 'command_execution', 'command': command, 'aggregated_output': '', 'exit_code': 0, 'status': 'completed'}}))\n"
        "print(json.dumps({'type': 'item.completed', 'item': {'id': 'i1', 'type': 'agent_message', 'text': 'fake final'}}))\n"
        "print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 7, 'cached_input_tokens': 2, 'output_tokens': 3, 'reasoning_output_tokens': 0}}))\n"
        "raise SystemExit(9 if prompt == 'fail' else 0)\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_run_codex_persists_real_process_trace_and_environment(tmp_path: Path) -> None:
    fake = tmp_path / "fake-codex"
    _write_fake_codex(fake)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    trace_path = tmp_path / "trace.jsonl"
    output_path = tmp_path / "last.txt"
    environment = build_condition_environment(Condition.ADAPTIVE, {"PATH": "/bin"})
    config = CodexRunConfig(
        model="gpt-eval", timeout_s=5, codex_executable=fake
    )

    result = run_codex(
        config,
        workspace=workspace,
        prompt="ok",
        environment=environment,
        trace_path=trace_path,
        output_last_message=output_path,
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.trace.final_message == "fake final"
    assert result.trace.metrics.total_tokens == 10
    assert "condition=adaptive" in result.trace.metrics.commands
    assert trace_path.read_text() == result.stdout
    assert output_path.read_text() == "fake final"


def test_run_codex_keeps_agent_failure_separate_from_trace(tmp_path: Path) -> None:
    fake = tmp_path / "fake-codex"
    _write_fake_codex(fake)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = CodexRunConfig(model="gpt-eval", timeout_s=5, codex_executable=fake)

    result = run_codex(
        config,
        workspace=workspace,
        prompt="fail",
        environment={"PATH": "/bin"},
        trace_path=tmp_path / "trace.jsonl",
        output_last_message=tmp_path / "last.txt",
    )

    assert result.exit_code == 9
    assert result.timed_out is False
    assert result.trace.metrics.total_tokens == 10


def test_run_codex_records_timeout_without_losing_partial_trace(tmp_path: Path) -> None:
    fake = tmp_path / "fake-codex"
    _write_fake_codex(fake)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = CodexRunConfig(model="gpt-eval", timeout_s=1, codex_executable=fake)

    result = run_codex(
        config,
        workspace=workspace,
        prompt="timeout",
        environment={"PATH": "/bin"},
        trace_path=tmp_path / "trace.jsonl",
        output_last_message=tmp_path / "last.txt",
    )

    assert result.exit_code == 124
    assert result.timed_out is True
    assert result.elapsed_ms >= 900
    assert "timed out" in result.stderr
    assert (tmp_path / "trace.jsonl").exists()
