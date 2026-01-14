from __future__ import annotations

import shlex
from typing import Iterable, Sequence


def assemble_prompt(messages: Iterable[dict]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def resolve_model_command(model: str, model_map: dict[str, str | Sequence[str]]) -> list[str]:
    prefix = model.split(":", 1)[0]
    if prefix in model_map:
        value = model_map[prefix]
        if isinstance(value, (list, tuple)):
            return list(value)
        return shlex.split(str(value))
    raise ValueError(f"Unknown model prefix: {prefix}")
