from __future__ import annotations

from tldr_bench.runners.cli_runner import run_cli_task
from tldr_bench.runners.dataset_context_runner import run_dataset_context
from tldr_bench.runners.dataset_runner import run_dataset
from tldr_bench.runners.openhands_runner import run_task as run_openhands
from tldr_bench.runners.static_context_runner import run_static


def run_task(task: dict, variant: str, run_config: dict | None = None) -> dict:
    runner = task.get("runner", "openhands")
    if runner == "static":
        return run_static(task, variant, run_config or {})
    if runner == "dataset":
        return run_dataset(task, variant, run_config or {})
    if runner == "dataset_context":
        return run_dataset_context(task, variant, run_config or {})
    if runner == "cli":
        return run_cli_task(task, variant, run_config or {})
    return run_openhands(task, variant)
