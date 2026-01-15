VARIANT_ID = "symbolkite"


def build_context(task: dict) -> str:
    from tldr_swinton.engines.symbolkite import get_relevant_context
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

    ctx = get_relevant_context(str(project), entry, depth=depth, language=language)
    return format_context(ctx, fmt=fmt, budget_tokens=budget)
