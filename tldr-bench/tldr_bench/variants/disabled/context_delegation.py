"""Context delegation variant for benchmarking.

This variant returns a retrieval PLAN instead of raw context,
enabling incremental context acquisition by agents.

IMPORTANT: Token counts from this variant are NOT directly comparable to
other variants. This variant outputs a plan (~200-500 tokens) that guides
the agent to retrieve context incrementally. The actual savings depend on:
1. Whether the agent follows the plan efficiently
2. Whether early steps provide enough context to skip later steps
3. The agent's ability to recognize when it has sufficient context

To properly benchmark context delegation:
- Compare total tokens used in a multi-turn agent execution WITH delegation
- vs. total tokens used with upfront context (symbolkite)
- This requires running an actual agent, not just measuring plan size
"""

VARIANT_ID = "context_delegation"

# Marker to indicate this is a workflow feature, not compression
VARIANT_TYPE = "workflow"
COMPARABLE_TO = []  # Not directly comparable to other variants


def build_context(task: dict) -> str:
    """Build context delegation plan for a task.

    Returns a retrieval plan that the agent can execute step-by-step
    instead of fetching all context upfront.

    NOTE: The returned token count measures PLAN SIZE only, not total
    tokens that would be used during incremental retrieval.
    """
    from tldr_swinton.modules.core.context_delegation import create_delegation_plan

    from . import resolve_project_root

    project = resolve_project_root(task)
    # Prefer explicit task_description, fall back to title/entry
    task_description = task.get("task_description", task.get("title", task.get("entry", "")))
    if not task_description:
        raise ValueError("task.task_description, task.title, or task.entry is required")

    budget = task.get("budget", 8000)
    focus_areas = task.get("expected_files", [])

    plan = create_delegation_plan(
        project=project,
        task_description=task_description,
        budget_tokens=budget,
        focus_areas=focus_areas,
    )

    return plan.format_for_agent()
