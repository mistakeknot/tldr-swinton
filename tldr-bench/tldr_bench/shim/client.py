from __future__ import annotations

from typing import Any


def build_prompt(user_prompt: str, context: str | None) -> str:
    if not context:
        return user_prompt
    return f"Context:\n{context}\n\nTask:\n{user_prompt}"


def build_context(
    project_root: str,
    entry: str,
    fmt: str,
    depth: int,
    budget_tokens: int | None,
) -> str:
    from tldr_swinton.api import get_relevant_context
    from tldr_swinton.output_formats import format_context

    ctx = get_relevant_context(project_root, entry, depth=depth, language="python")
    return format_context(ctx, fmt=fmt, budget_tokens=budget_tokens)


def build_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
