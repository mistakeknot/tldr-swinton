from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .codex_runner import _invokes_tldrs, _raw_read_paths
from .schema import TraceMetrics


_CLAUDE_TOOLS = "Bash,Read,Edit,Write,Glob,Grep"


@dataclass(frozen=True)
class ClaudeRunConfig:
    model: str
    reasoning_effort: str = "medium"
    timeout_s: int = 900
    claude_executable: Path = Path("claude")
    max_turns: int = 100
    max_budget_usd: float = 5.0


@dataclass(frozen=True)
class ParsedClaudeTrace:
    session_id: str | None
    final_message: str
    metrics: TraceMetrics


@dataclass(frozen=True)
class ClaudeProcessResult:
    exit_code: int
    timed_out: bool
    elapsed_ms: int
    stdout: str
    stderr: str
    trace: ParsedClaudeTrace


def build_claude_command(
    config: ClaudeRunConfig,
    *,
    workspace: Path,
    prompt: str,
    guidance: str,
) -> list[str]:
    del workspace  # subprocess cwd is the authoritative project root.
    return [
        str(config.claude_executable),
        "-p",
        "--safe-mode",
        "--no-session-persistence",
        "--no-chrome",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--prompt-suggestions",
        "false",
        "--tools",
        _CLAUDE_TOOLS,
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        config.model,
        "--effort",
        config.reasoning_effort,
        "--max-turns",
        str(config.max_turns),
        "--max-budget-usd",
        str(config.max_budget_usd),
        "--append-system-prompt",
        guidance,
        prompt,
    ]


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _content_bytes(content: Any) -> int:
    if isinstance(content, str):
        return len(content.encode())
    if isinstance(content, list):
        return sum(_content_bytes(item) for item in content)
    if isinstance(content, dict):
        if content.get("type") == "text":
            return _content_bytes(content.get("text"))
        return len(json.dumps(content, sort_keys=True).encode())
    return 0


def _read_tool_path(tool_input: Any) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    value = tool_input.get("file_path") or tool_input.get("path")
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).as_posix()
    return path[2:] if path.startswith("./") else path


def parse_claude_trace(text: str, *, requested_model: str) -> ParsedClaudeTrace:
    session_id: str | None = None
    model = requested_model
    final_message = ""
    commands: list[str] = []
    errors: list[str] = []
    tool_calls = 0
    tool_output_bytes = 0
    tldrs_calls = 0
    raw_read_calls = 0
    raw_read_paths: list[str] = []
    compactions = 0
    usage: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"non-json trace line: {line}")
            continue
        if not isinstance(event, dict):
            errors.append(f"non-object trace event: {line}")
            continue

        event_type = event.get("type")
        if event_type == "system":
            session_id = str(event.get("session_id") or session_id or "") or None
            if event.get("subtype") == "init" and event.get("model"):
                model = str(event["model"])
            if event.get("subtype") == "compact_boundary":
                compactions += 1
        elif event_type == "assistant":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                name = str(block.get("name") or "")
                tool_input = block.get("input")
                if name == "Bash" and isinstance(tool_input, dict):
                    command = tool_input.get("command")
                    if isinstance(command, str):
                        commands.append(command)
                        if _invokes_tldrs(command):
                            tldrs_calls += 1
                        paths = _raw_read_paths(command)
                        if paths:
                            raw_read_calls += 1
                            raw_read_paths.extend(paths)
                elif name == "Read":
                    path = _read_tool_path(tool_input)
                    if path is not None:
                        raw_read_calls += 1
                        raw_read_paths.append(path)
        elif event_type == "user":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    tool_output_bytes += _content_bytes(block.get("content"))
                    if block.get("is_error"):
                        errors.append("Claude tool call failed")
        elif event_type == "result":
            session_id = str(event.get("session_id") or session_id or "") or None
            result = event.get("result")
            if isinstance(result, str):
                final_message = result
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            if event.get("is_error"):
                errors.append(str(event.get("result") or event.get("subtype") or "Claude run failed"))

    if usage is None:
        input_tokens = cached_input_tokens = output_tokens = total_tokens = None
    else:
        direct_input = int(usage.get("input_tokens") or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
        cached_input_tokens = int(usage.get("cache_read_input_tokens") or 0)
        input_tokens = direct_input + cache_creation + cached_input_tokens
        output_tokens = int(usage.get("output_tokens") or 0)
        total_tokens = input_tokens + output_tokens

    unique_raw_read_paths = tuple(dict.fromkeys(raw_read_paths))
    return ParsedClaudeTrace(
        session_id=session_id,
        final_message=final_message,
        metrics=TraceMetrics(
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_output_tokens=None,
            total_tokens=total_tokens,
            tool_calls=tool_calls,
            tool_output_bytes=tool_output_bytes,
            tldrs_calls=tldrs_calls,
            raw_read_calls=raw_read_calls,
            raw_read_paths=tuple(raw_read_paths),
            unique_raw_read_paths=unique_raw_read_paths,
            duplicate_raw_read_paths=len(raw_read_paths) - len(unique_raw_read_paths),
            compactions=compactions,
            commands=tuple(commands),
            errors=tuple(errors),
        ),
    )


def run_claude(
    config: ClaudeRunConfig,
    *,
    workspace: Path,
    prompt: str,
    guidance: str,
    environment: dict[str, str],
    trace_path: Path,
    output_last_message: Path,
) -> ClaudeProcessResult:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    output_last_message.parent.mkdir(parents=True, exist_ok=True)
    command = build_claude_command(
        config,
        workspace=workspace,
        prompt=prompt,
        guidance=guidance,
    )
    started = time.perf_counter()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=config.timeout_s,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = _text(exc.stdout)
        stderr = _text(exc.stderr)
        if stderr and not stderr.endswith("\n"):
            stderr += "\n"
        stderr += f"claude timed out after {config.timeout_s}s"
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    trace_path.write_text(stdout)
    parsed = parse_claude_trace(stdout, requested_model=config.model)
    output_last_message.write_text(parsed.final_message)
    return ClaudeProcessResult(
        exit_code=exit_code,
        timed_out=timed_out,
        elapsed_ms=elapsed_ms,
        stdout=stdout,
        stderr=stderr,
        trace=parsed,
    )
