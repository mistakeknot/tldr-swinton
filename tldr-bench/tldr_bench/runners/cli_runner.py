from __future__ import annotations

import json
import re
import subprocess
from typing import Any


def _read_last_log(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if line.strip()]
    except FileNotFoundError:
        return {}
    if not lines:
        return {}
    return json.loads(lines[-1])


def _parse_int(value: str) -> int | None:
    cleaned = value.replace(",", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _extract_usage(text: str) -> dict[str, int | None]:
    usage: dict[str, int | None] = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    if not text:
        return usage

    patterns = {
        "prompt_tokens": r"(prompt tokens|prompt_tokens)[:\s]+([0-9,]+)",
        "completion_tokens": r"(completion tokens|completion_tokens)[:\s]+([0-9,]+)",
        "total_tokens": r"(total tokens|total_tokens|tokens used)[:\s]+([0-9,]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            parsed = _parse_int(match.group(2))
            if parsed is not None:
                usage[key] = parsed
    return usage


def run_cli_task(task: dict, variant: str, run_config: dict) -> dict:
    result = subprocess.run(
        task["bench_command"],
        text=True,
        capture_output=True,
        check=False,
    )
    status = "completed" if result.returncode == 0 else "failed"
    shim_data = _read_last_log(run_config.get("shim_log_path"))
    usage = shim_data.get("usage", {})
    if not usage:
        parsed = _extract_usage("\n".join([result.stdout, result.stderr]))
        usage = {k: v for k, v in parsed.items() if v is not None}
    return {
        "task_id": task.get("id"),
        "variant_id": variant,
        "status": status,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
