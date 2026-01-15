from __future__ import annotations

from typing import Any, Mapping

from .schema import BenchInstance


_PROMPT_KEYS = (
    "input",
    "prompt",
    "question",
)

_ID_KEYS = (
    "id",
    "task_id",
    "instance_id",
)


def normalize_record(record: Mapping[str, Any]) -> BenchInstance:
    raw_id = ""
    for key in _ID_KEYS:
        value = record.get(key)
        if value:
            raw_id = str(value).strip()
            break
    if not raw_id:
        raise ValueError("LongBench record missing id")

    dataset_name = record.get("dataset")
    if dataset_name:
        instance_id = f"{dataset_name}:{raw_id}"
    else:
        instance_id = raw_id

    prompt = ""
    for key in _PROMPT_KEYS:
        value = record.get(key)
        if value:
            prompt = str(value)
            break
    if not prompt:
        raise ValueError(f"LongBench record {instance_id} missing prompt")

    split = record.get("split") or record.get("subset")
    metadata = {
        k: v
        for k, v in record.items()
        if k not in set(_ID_KEYS) | set(_PROMPT_KEYS) | {"split", "subset"}
    }

    return BenchInstance(
        instance_id=instance_id,
        prompt=prompt,
        dataset="longbench",
        split=str(split) if split else None,
        metadata=metadata,
    )
