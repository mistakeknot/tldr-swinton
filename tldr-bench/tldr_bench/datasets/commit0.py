from __future__ import annotations

from typing import Any, Mapping

from .schema import BenchInstance


_PROMPT_KEYS = (
    "prompt",
    "instruction",
    "question",
    "task",
    "description",
)


def normalize_record(record: Mapping[str, Any]) -> BenchInstance:
    instance_id = str(
        record.get("instance_id")
        or record.get("task_id")
        or record.get("id")
        or ""
    ).strip()
    if not instance_id:
        raise ValueError("Commit0 record missing instance_id")

    prompt = ""
    for key in _PROMPT_KEYS:
        value = record.get(key)
        if value:
            prompt = str(value)
            break
    if not prompt:
        raise ValueError(f"Commit0 record {instance_id} missing prompt")

    repo = record.get("repo") or record.get("repo_name")
    base_commit = record.get("base_commit")

    metadata = {
        k: v
        for k, v in record.items()
        if k not in {"instance_id", "task_id", "id", "repo", "repo_name", "base_commit"} | set(_PROMPT_KEYS)
    }

    return BenchInstance(
        instance_id=instance_id,
        prompt=prompt,
        dataset="commit0",
        repo=repo,
        base_commit=base_commit,
        metadata=metadata,
    )
