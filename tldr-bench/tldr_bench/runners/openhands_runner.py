from typing import Any


def run_task(task: dict[str, Any], variant: str) -> dict[str, Any]:
    """Run a single task using the OpenHands harness (placeholder)."""
    task_id = task.get("id")
    if not task_id:
        raise ValueError("task.id is required")
    if not variant:
        raise ValueError("variant is required")
    return {"task_id": task_id, "variant_id": variant, "status": "not_implemented"}
