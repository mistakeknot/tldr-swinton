from typing import Any
import subprocess
import os

from tldr_bench.openhands import resolve_bench_dir


def run_task(task: dict[str, Any], variant: str) -> dict[str, Any]:
    """Run a single task using the OpenHands harness (placeholder)."""
    task_id = task.get("id")
    if not task_id:
        raise ValueError("task.id is required")
    if not variant:
        raise ValueError("variant is required")
    bench_command = task.get("bench_command")
    if bench_command:
        result = subprocess.run(
            bench_command,
            text=True,
            capture_output=True,
            check=False,
        )
        status = "completed" if result.returncode == 0 else "failed"
        return {
            "task_id": task_id,
            "variant_id": variant,
            "status": status,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

    try:
        bench_dir = resolve_bench_dir()
    except FileNotFoundError:
        bench_dir = None

    llm_config = task.get("llm_config") or os.getenv("OH_LLM_CONFIG")
    benchmark = task.get("benchmark")
    if bench_dir and llm_config and benchmark:
        command = ["uv", "run", f"{benchmark}-infer", llm_config]
        select = task.get("select")
        if select:
            command.extend(["--select", select])
        result = subprocess.run(
            command,
            cwd=bench_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        status = "completed" if result.returncode == 0 else "failed"
        return {
            "task_id": task_id,
            "variant_id": variant,
            "status": status,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "bench_dir": str(bench_dir),
            "command": command,
        }

    return {
        "task_id": task_id,
        "variant_id": variant,
        "status": "not_implemented",
        "bench_dir": str(bench_dir) if bench_dir else None,
    }
