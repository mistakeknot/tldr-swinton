from __future__ import annotations

from typing import Any, Mapping

from .schema import BenchInstance


_PROMPT_KEYS = (
    "prompt",
    "input",
    "question",
)

_ID_KEYS = (
    "id",
    "task_id",
    "instance_id",
)


def normalize_record(record: Mapping[str, Any]) -> BenchInstance:
    instance_id = ""
    for key in _ID_KEYS:
        value = record.get(key)
        if value:
            instance_id = str(value).strip()
            break
    if not instance_id:
        raise ValueError("RepoBench record missing id")

    prompt = ""
    for key in _PROMPT_KEYS:
        value = record.get(key)
        if value:
            prompt = str(value)
            break
    if not prompt:
        raise ValueError(f"RepoBench record {instance_id} missing prompt")

    split = record.get("split")
    metadata = {
        k: v
        for k, v in record.items()
        if k not in set(_ID_KEYS) | set(_PROMPT_KEYS) | {"split"}
    }

    return BenchInstance(
        instance_id=instance_id,
        prompt=prompt,
        dataset="repobench",
        split=str(split) if split else None,
        metadata=metadata,
    )
