VARIANT_ID = "difflens"


def build_context(task: dict) -> str:
    from tldr_swinton.api import get_diff_context
    from tldr_swinton.output_formats import format_context_pack

    from . import resolve_project_root

    project = resolve_project_root(task)
    language = task.get("language", "python")
    budget = task.get("budget")
    base = task.get("base")
    head = task.get("head", "HEAD")

    pack = get_diff_context(
        str(project),
        base=base,
        head=head,
        budget_tokens=budget,
        language=language,
    )
    return format_context_pack(pack, fmt="ultracompact")
