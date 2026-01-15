VARIANT_ID = "difflens"


def build_context(task: dict) -> str:
    from tldr_swinton.engines.difflens import get_diff_context
    from tldr_swinton.output_formats import format_context_pack

    from . import resolve_project_root

    project = resolve_project_root(task)
    base = task.get("base")
    head = task.get("head")
    budget = task.get("budget")
    language = task.get("language", "python")
    fmt = task.get("context_format", "ultracompact")

    pack = get_diff_context(project, base=base, head=head, budget_tokens=budget, language=language)
    return format_context_pack(pack, fmt=fmt)
