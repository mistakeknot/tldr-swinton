from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .schema import TraceMetrics


_RAW_READ_COMMAND = re.compile(
    r"(?:^|[;&|]\s*|['\"])(?:cat|sed|head|tail)(?:\s|$)"
)
_TOOL_ITEM_TYPES = {
    "command_execution",
    "mcp_tool_call",
    "function_call",
    "web_search",
}
_SHELL_NAMES = {"bash", "dash", "ksh", "sh", "zsh"}
_SHELL_BOUNDARIES = {";", "&&", "||", "|", "&", "(", ")"}
_SHELL_KEYWORDS = {"if", "then", "elif", "else", "while", "until", "do"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_HEREDOC = re.compile(
    r"<<-?\s*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)"
)


def _unwrap_shell_script(command: str) -> str:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command
    if not tokens or Path(tokens[0]).name not in _SHELL_NAMES:
        return command
    for index, token in enumerate(tokens[1:], 1):
        if token.startswith("-") and "c" in token[1:] and index + 1 < len(tokens):
            return tokens[index + 1]
    return command


def _strip_heredoc_bodies(script: str) -> str:
    kept: list[str] = []
    delimiter: str | None = None
    for line in script.splitlines():
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        match = _HEREDOC.search(line)
        if match:
            kept.append(line[: match.start()])
            delimiter = match.group("delimiter")
        else:
            kept.append(line)
    return "\n".join(kept)


def _invokes_tldrs(command: str) -> bool:
    script = _strip_heredoc_bodies(_unwrap_shell_script(command))
    lexer = shlex.shlex(
        script.replace("\n", " ; "),
        posix=True,
        punctuation_chars=";&|()",
    )
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return False

    expect_command = True
    command_wrapper = False
    environment_wrapper = False
    for token in tokens:
        if token in _SHELL_BOUNDARIES:
            expect_command = True
            command_wrapper = False
            environment_wrapper = False
            continue
        if not expect_command:
            continue
        if token in _SHELL_KEYWORDS or token == "!" or _ASSIGNMENT.match(token):
            continue
        executable = Path(token).name
        if executable == "env":
            environment_wrapper = True
            continue
        if environment_wrapper and token.startswith("-"):
            continue
        if executable == "command":
            command_wrapper = True
            continue
        if command_wrapper and token in {"-v", "-V"}:
            expect_command = False
            continue
        if command_wrapper and token.startswith("-"):
            continue
        if executable == "tldrs":
            return True
        expect_command = False
    return False


@dataclass(frozen=True)
class CodexRunConfig:
    model: str
    reasoning_effort: str = "medium"
    timeout_s: int = 900
    codex_executable: Path = Path("codex")
    sandbox: str = "workspace-write"


@dataclass(frozen=True)
class ParsedCodexTrace:
    thread_id: str | None
    final_message: str
    metrics: TraceMetrics


@dataclass(frozen=True)
class CodexProcessResult:
    exit_code: int
    timed_out: bool
    elapsed_ms: int
    stdout: str
    stderr: str
    trace: ParsedCodexTrace


def build_codex_command(
    config: CodexRunConfig,
    *,
    workspace: Path,
    prompt: str,
    output_last_message: Path,
) -> list[str]:
    return [
        str(config.codex_executable),
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--json",
        "--color",
        "never",
        "--sandbox",
        config.sandbox,
        "--model",
        config.model,
        "-c",
        'approval_policy="never"',
        "-c",
        f'model_reasoning_effort="{config.reasoning_effort}"',
        "-C",
        str(workspace.resolve()),
        "--output-last-message",
        str(output_last_message.resolve()),
        prompt,
    ]


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def parse_codex_trace(text: str, *, requested_model: str) -> ParsedCodexTrace:
    thread_id: str | None = None
    final_message = ""
    commands: list[str] = []
    errors: list[str] = []
    tool_calls = 0
    tool_output_bytes = 0
    tldrs_calls = 0
    raw_read_calls = 0
    compactions = 0
    input_tokens = 0
    cached_input_tokens = 0
    output_tokens = 0
    reasoning_output_tokens = 0
    saw_usage = False

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

        event_type = str(event.get("type", ""))
        if event_type == "thread.started":
            thread_id = event.get("thread_id")
        if "compact" in event_type.lower():
            compactions += 1
        if event_type == "error":
            errors.append(str(event.get("message", "unknown Codex error")))

        item = event.get("item")
        if event_type == "item.completed" and isinstance(item, dict):
            item_type = str(item.get("type", ""))
            if "compact" in item_type.lower():
                compactions += 1
            if item_type == "agent_message":
                final_message = str(item.get("text", ""))
            if item_type in _TOOL_ITEM_TYPES:
                tool_calls += 1
                tool_output_bytes += len(
                    str(item.get("aggregated_output", "")).encode("utf-8")
                )
            if item_type == "command_execution":
                command = str(item.get("command", ""))
                commands.append(command)
                if _invokes_tldrs(command):
                    tldrs_calls += 1
                if _RAW_READ_COMMAND.search(command):
                    raw_read_calls += 1
                exit_code = item.get("exit_code")
                if isinstance(exit_code, int) and exit_code != 0:
                    errors.append(f"command failed ({exit_code}): {command}")

        usage = event.get("usage")
        if event_type == "turn.completed" and isinstance(usage, dict):
            saw_usage = True
            input_tokens += int(usage.get("input_tokens") or 0)
            cached_input_tokens += int(usage.get("cached_input_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or 0)
            reasoning_output_tokens += int(
                usage.get("reasoning_output_tokens") or 0
            )

    return ParsedCodexTrace(
        thread_id=thread_id,
        final_message=final_message,
        metrics=TraceMetrics(
            model=requested_model,
            input_tokens=input_tokens if saw_usage else None,
            cached_input_tokens=cached_input_tokens if saw_usage else None,
            output_tokens=output_tokens if saw_usage else None,
            reasoning_output_tokens=(
                reasoning_output_tokens if saw_usage else None
            ),
            total_tokens=(input_tokens + output_tokens) if saw_usage else None,
            tool_calls=tool_calls,
            tool_output_bytes=tool_output_bytes,
            tldrs_calls=tldrs_calls,
            raw_read_calls=raw_read_calls,
            compactions=compactions,
            commands=tuple(commands),
            errors=tuple(errors),
        ),
    )


def run_codex(
    config: CodexRunConfig,
    *,
    workspace: Path,
    prompt: str,
    environment: dict[str, str],
    trace_path: Path,
    output_last_message: Path,
) -> CodexProcessResult:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    output_last_message.parent.mkdir(parents=True, exist_ok=True)
    command = build_codex_command(
        config,
        workspace=workspace,
        prompt=prompt,
        output_last_message=output_last_message,
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
        stderr += f"codex timed out after {config.timeout_s}s"
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    trace_path.write_text(stdout)
    parsed = parse_codex_trace(stdout, requested_model=config.model)
    return CodexProcessResult(
        exit_code=exit_code,
        timed_out=timed_out,
        elapsed_ms=elapsed_ms,
        stdout=stdout,
        stderr=stderr,
        trace=parsed,
    )
