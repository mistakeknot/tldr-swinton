from __future__ import annotations

from pathlib import Path
import statistics

from tldr_bench.datasets import load_dataset, select_instances
from tldr_bench.metrics import TokenTiming, count_tokens
from tldr_bench.variants import get_variant


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


def _resolve_dataset_path(dataset_path: str) -> Path:
    path = Path(dataset_path)
    if path.is_absolute():
        return path

    base = Path(__file__).resolve().parents[2]
    if path.parts and path.parts[0] == "tldr-bench":
        base = Path(__file__).resolve().parents[3]
    return base / path


def run_dataset_context(task: dict, variant: str, run_config: dict) -> dict:
    dataset_path_value = task.get("dataset_path") or task.get("dataset")
    if not dataset_path_value:
        raise ValueError("dataset_path or dataset is required for dataset_context runner")

    dataset_path = _resolve_dataset_path(dataset_path_value)

    timing = TokenTiming()
    with timing.section("dataset_load"):
        instances = load_dataset(dataset_path, kind=task.get("dataset_kind"))

    instance_ids = _resolve_instance_ids(task, run_config)
    selected = select_instances(instances, instance_ids)

    tokenizer_model = run_config.get("tokenizer_model") if run_config else None

    with timing.section("context"):
        context = get_variant(variant).build_context(task)
    context_tokens = count_tokens(context, tokenizer_model)
    context_bytes = len(context.encode("utf-8"))

    with timing.section("prompt"):
        prompt_tokens = [count_tokens(inst.prompt, tokenizer_model) for inst in selected]

    prompt_total = sum(prompt_tokens)
    prompt_min = min(prompt_tokens) if prompt_tokens else 0
    prompt_max = max(prompt_tokens) if prompt_tokens else 0
    prompt_median = int(statistics.median(prompt_tokens)) if prompt_tokens else 0
    prompt_bytes = sum(len(inst.prompt.encode("utf-8")) for inst in selected)

    total_tokens = [tokens + context_tokens for tokens in prompt_tokens]
    total_total = sum(total_tokens)
    total_min = min(total_tokens) if total_tokens else 0
    total_max = max(total_tokens) if total_tokens else 0
    total_median = int(statistics.median(total_tokens)) if total_tokens else 0

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
        "context_bytes": context_bytes,
        "context_tokens": context_tokens,
        "prompt_tokens_total": prompt_total,
        "prompt_tokens_min": prompt_min,
        "prompt_tokens_max": prompt_max,
        "prompt_tokens_median": prompt_median,
        "prompt_bytes_total": prompt_bytes,
        "total_tokens_total": total_total,
        "total_tokens_min": total_min,
        "total_tokens_max": total_max,
        "total_tokens_median": total_median,
        **timing.to_dict(),
    }
