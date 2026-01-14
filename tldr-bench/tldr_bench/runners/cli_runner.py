from __future__ import annotations

import json
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
