from __future__ import annotations

from tldr_bench.metrics import TokenTiming, count_tokens
from tldr_bench.variants import get_variant


def run_static(task: dict, variant: str, run_config: dict) -> dict:
    timing = TokenTiming()
    with timing.section("context"):
        ctx = get_variant(variant).build_context(task)
    tokenizer_model = run_config.get("tokenizer_model")
    return {
        "task_id": task.get("id"),
        "variant_id": variant,
        "status": "completed",
        "context_bytes": len(ctx.encode("utf-8")),
        "context_tokens_estimate": count_tokens(ctx, tokenizer_model),
        **timing.to_dict(),
    }
