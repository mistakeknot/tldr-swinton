"""Attention-weighted pruning variant for benchmarking.

This variant uses historical usage patterns to prune unlikely-to-be-used
context, reducing wasted tokens.
"""

VARIANT_ID = "attention_pruning"


def build_context(task: dict) -> str:
    """Build attention-pruned context for a task.

    Uses historical usage patterns to prune context that is
    unlikely to be used based on past agent behavior.
    """
    from tldr_swinton.engines.symbolkite import get_relevant_context
    from tldr_swinton.modules.core.attention_pruning import (
        AttentionTracker,
        create_attention_reranker,
    )
    from tldr_swinton.output_formats import format_context

    from . import resolve_project_root

    project = resolve_project_root(task)
    entry = task.get("entry", "")
    if not entry:
        raise ValueError("task.entry is required")

    depth = task.get("depth", 1)
    language = task.get("language", "python")
    budget = task.get("budget")
    fmt = task.get("context_format", "text")

    # Get base context
    ctx = get_relevant_context(str(project), entry, depth=depth, language=language)

    # Apply attention-based pruning if tracker exists
    tracker = AttentionTracker(project)
    reranker = create_attention_reranker(tracker)

    # Convert context slices to candidates format
    if isinstance(ctx, dict) and "slices" in ctx:
        candidates = [
            {"symbol_id": s.get("id", s.get("name", "")), "relevance": 0.5, **s}
            for s in ctx.get("slices", [])
        ]
        if candidates:
            reranked = reranker(candidates)
            # Prune bottom 30% by combined score
            cutoff = int(len(reranked) * 0.7)
            pruned_ids = {c["symbol_id"] for c in reranked[cutoff:]}
            ctx["slices"] = [
                s for s in ctx.get("slices", [])
                if s.get("id", s.get("name", "")) not in pruned_ids
            ]

    return format_context(ctx, fmt=fmt, budget_tokens=budget)
