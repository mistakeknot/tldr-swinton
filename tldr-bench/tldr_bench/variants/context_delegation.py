"""Context delegation variant for benchmarking.

This variant returns a retrieval plan instead of raw context,
enabling incremental context acquisition.
"""

VARIANT_ID = "context_delegation"


def build_context(task: dict) -> str:
    """Build context delegation plan for a task.

    Returns a retrieval plan that the agent can execute step-by-step
    instead of fetching all context upfront.
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
