from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

from tldr_bench.agent_eval.claude_runner import (
    ClaudeRunConfig,
    build_claude_command,
    parse_claude_trace,
    run_claude,
)


def test_parse_current_claude_stream_json_trace() -> None:
    trace = "\n".join(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "init",
                    "session_id": "session-123",
                    "model": "claude-sonnet-5",
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {
                                    "command": "sed -n '1,40p' src/owner.py"
                                },
                            },
                            {
                                "type": "tool_use",
                                "name": "Read",
                                "input": {"file_path": "src/owner.py"},
                            },
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "content": "source output",
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "Implemented and verified.",
                    "session_id": "session-123",
                    "usage": {
                        "input_tokens": 100,
                        "cache_creation_input_tokens": 200,
                        "cache_read_input_tokens": 300,
                        "output_tokens": 50,
                    },
                }
            ),
        ]
    )

    parsed = parse_claude_trace(trace, requested_model="sonnet")

    assert parsed.session_id == "session-123"
    assert parsed.final_message == "Implemented and verified."
    assert parsed.metrics.model == "claude-sonnet-5"
    assert parsed.metrics.input_tokens == 600
    assert parsed.metrics.cached_input_tokens == 300
    assert parsed.metrics.output_tokens == 50
    assert parsed.metrics.reasoning_output_tokens is None
    assert parsed.metrics.total_tokens == 650
    assert parsed.metrics.uncached_total_tokens == 350
    assert parsed.metrics.tool_calls == 2
    assert parsed.metrics.tool_output_bytes == len("source output".encode())
    assert parsed.metrics.raw_read_calls == 2
    assert parsed.metrics.raw_read_paths == ("src/owner.py", "src/owner.py")
    assert parsed.metrics.unique_raw_read_paths == ("src/owner.py",)
    assert parsed.metrics.duplicate_raw_read_paths == 1


def test_build_claude_command_isolates_harness_and_injects_guidance(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = ClaudeRunConfig(
        model="sonnet",
        reasoning_effort="medium",
        timeout_s=60,
        claude_executable=Path("/opt/tools/claude"),
    )

    command = build_claude_command(
        config,
        workspace=workspace,
        prompt="Repair the bug.",
        guidance="Use bounded context.",
    )

    assert command[0] == "/opt/tools/claude"
    assert "-p" in command
    assert "--safe-mode" in command
    assert "--no-session-persistence" in command
    assert "--strict-mcp-config" in command
    assert "--disable-slash-commands" in command
    assert command[command.index("--permission-mode") + 1] == "bypassPermissions"
    assert command[command.index("--output-format") + 1] == "stream-json"
    assert command[command.index("--model") + 1] == "sonnet"
    assert command[command.index("--effort") + 1] == "medium"
    assert command[command.index("--append-system-prompt") + 1] == (
        "Use bounded context."
    )
    assert command[-1] == "Repair the bug."


def _write_fake_claude(path: Path) -> None:
    path.write_text(
        "#!" + sys.executable + "\n"
        "import json\n"
        "print(json.dumps({'type': 'system', 'subtype': 'init', "
        "'session_id': 'fake-session', 'model': 'claude-test'}))\n"
        "print(json.dumps({'type': 'result', 'subtype': 'success', "
        "'is_error': False, 'result': 'fake final', "
        "'session_id': 'fake-session', 'usage': {'input_tokens': 7, "
        "'cache_creation_input_tokens': 2, 'cache_read_input_tokens': 1, "
        "'output_tokens': 3}}))\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_run_claude_persists_trace_and_final_message(tmp_path: Path) -> None:
    fake = tmp_path / "fake-claude"
    _write_fake_claude(fake)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    trace_path = tmp_path / "trace.jsonl"
    output_path = tmp_path / "last.txt"
    config = ClaudeRunConfig(
        model="sonnet", timeout_s=5, claude_executable=fake
    )

    result = run_claude(
        config,
        workspace=workspace,
        prompt="ok",
        guidance="Solve the task.",
        environment={"PATH": "/bin"},
        trace_path=trace_path,
        output_last_message=output_path,
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.trace.final_message == "fake final"
    assert result.trace.metrics.total_tokens == 13
    assert trace_path.read_text() == result.stdout
    assert output_path.read_text() == "fake final"
