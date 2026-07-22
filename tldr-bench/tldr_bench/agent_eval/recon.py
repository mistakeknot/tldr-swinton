"""Production task-context implementation used by the agent evaluator.

Keeping this as a re-export makes the hidden-grader campaign exercise exactly
the packet code shipped by tldr-swinton instead of a benchmark-only copy.
"""

from tldr_swinton.modules.core.task_context import (
    ReconExcerpt,
    rank_source_excerpts,
    render_bounded_context,
)

__all__ = ["ReconExcerpt", "rank_source_excerpts", "render_bounded_context"]
