from __future__ import annotations

from typing import Any, Mapping

from .schema import BenchInstance


_PROMPT_KEYS = (
    "problem_statement",
    "prompt",
    "question",
)


def normalize_record(record: Mapping[str, Any]) -> BenchInstance:
    instance_id = str(record.get("instance_id") or record.get("id") or "").strip()
    if not instance_id:
        raise ValueError("SWE-bench record missing instance_id")

    prompt = ""
    for key in _PROMPT_KEYS:
        value = record.get(key)
        if value:
            prompt = str(value)
            break
    if not prompt:
        raise ValueError(f"SWE-bench record {instance_id} missing prompt")

    repo = record.get("repo")
    base_commit = record.get("base_commit")

    metadata = {k: v for k, v in record.items() if k not in {"instance_id", "id", "repo", "base_commit"} | set(_PROMPT_KEYS)}

    return BenchInstance(
        instance_id=instance_id,
        prompt=prompt,
        dataset="swebench",
        repo=repo,
        base_commit=base_commit,
        metadata=metadata,
    )
