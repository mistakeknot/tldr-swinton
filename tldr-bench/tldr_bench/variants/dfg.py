VARIANT_ID = "dfg"


def build_context(task: dict) -> str:
    from tldr_swinton.engines.dfg import get_dfg_context

    from .helpers import format_json, parse_entry

    language = task.get("language", "python")
    fmt = task.get("context_format", "json")
    file_path, func_name = parse_entry(task)

    ctx = get_dfg_context(str(file_path), func_name, language=language)
    return format_json(ctx, fmt)
