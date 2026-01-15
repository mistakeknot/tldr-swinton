from __future__ import annotations

from pathlib import Path
import statistics
from typing import Iterable

from tldr_bench.datasets import load_dataset, select_instances
from tldr_bench.metrics import TokenTiming, count_tokens


def _parse_instance_ids(value: str | list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    tokens = [item.strip() for item in value.split(",") if item.strip()]
    return tokens or None


def _resolve_instance_ids(task: dict, run_config: dict | None) -> list[str] | None:
    if run_config:
        value = run_config.get("instance_ids")
        parsed = _parse_instance_ids(value)
        if parsed:
            return parsed
    return _parse_instance_ids(task.get("instance_ids"))


def run_dataset(task: dict, variant: str, run_config: dict) -> dict:
    dataset_path = task.get("dataset_path") or task.get("dataset")
    if not dataset_path:
        raise ValueError("dataset_path or dataset is required for dataset runner")

    dataset_path = Path(dataset_path)
    if not dataset_path.is_absolute():
        base = Path(__file__).resolve().parents[2]
        if dataset_path.parts and dataset_path.parts[0] == "tldr-bench":
            base = Path(__file__).resolve().parents[3]
        dataset_path = base / dataset_path

    timing = TokenTiming()
    with timing.section("dataset_load"):
        instances = load_dataset(dataset_path, kind=task.get("dataset_kind"))

    instance_ids = _resolve_instance_ids(task, run_config)
    selected = select_instances(instances, instance_ids)

    tokenizer_model = run_config.get("tokenizer_model") if run_config else None

    with timing.section("prompt"):
        prompt_tokens = [count_tokens(inst.prompt, tokenizer_model) for inst in selected]

    prompt_total = sum(prompt_tokens)
    prompt_min = min(prompt_tokens) if prompt_tokens else 0
    prompt_max = max(prompt_tokens) if prompt_tokens else 0
    prompt_median = int(statistics.median(prompt_tokens)) if prompt_tokens else 0
    prompt_bytes = sum(len(inst.prompt.encode("utf-8")) for inst in selected)

    status = "completed"
    if not selected:
        status = "empty"

    return {
        "task_id": task.get("id"),
        "variant_id": variant,
        "status": status,
        "dataset_path": str(dataset_path),
        "dataset_kind": task.get("dataset_kind") or "auto",
        "instances_total": len(instances),
        "instances_selected": len(selected),
        "prompt_tokens_total": prompt_total,
        "prompt_tokens_min": prompt_min,
        "prompt_tokens_max": prompt_max,
        "prompt_tokens_median": prompt_median,
        "prompt_bytes_total": prompt_bytes,
        **timing.to_dict(),
    }
