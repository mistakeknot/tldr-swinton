from typing import Any

from tldr_bench.openhands import resolve_bench_dir


def run_task(task: dict[str, Any], variant: str) -> dict[str, Any]:
    """Run a single task using the OpenHands harness (placeholder)."""
    task_id = task.get("id")
    if not task_id:
        raise ValueError("task.id is required")
    if not variant:
        raise ValueError("variant is required")
    try:
        bench_dir = resolve_bench_dir()
    except FileNotFoundError:
        bench_dir = None
    return {
        "task_id": task_id,
        "variant_id": variant,
        "status": "not_implemented",
        "bench_dir": str(bench_dir) if bench_dir else None,
    }
