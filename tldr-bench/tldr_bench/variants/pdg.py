VARIANT_ID = "pdg"


def build_context(task: dict) -> str:
    from tldr_swinton.engines.pdg import get_pdg_context

    from .helpers import format_json, parse_entry

    language = task.get("language", "python")
    fmt = task.get("context_format", "json")
    file_path, func_name = parse_entry(task)

    ctx = get_pdg_context(str(file_path), func_name, language=language)
    if ctx is None:
        ctx = {"function": func_name, "nodes": 0, "edges": []}
    return format_json(ctx, fmt)
