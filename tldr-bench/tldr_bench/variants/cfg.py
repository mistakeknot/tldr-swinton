VARIANT_ID = "cfg"


def build_context(task: dict) -> str:
    from tldr_swinton.engines.cfg import get_cfg_context

    from .helpers import format_json, parse_entry

    language = task.get("language", "python")
    fmt = task.get("context_format", "json")
    file_path, func_name = parse_entry(task)

    ctx = get_cfg_context(str(file_path), func_name, language=language)
    return format_json(ctx, fmt)
