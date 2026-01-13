from __future__ import annotations

from typing import Iterable


def assemble_prompt(messages: Iterable[dict]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def resolve_model_command(model: str, model_map: dict[str, str]) -> str:
    prefix = model.split(":", 1)[0]
    if prefix in model_map:
        return model_map[prefix]
    raise ValueError(f"Unknown model prefix: {prefix}")
