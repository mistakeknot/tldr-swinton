VARIANT_ID = "slice"


def build_context(task: dict) -> str:
    from tldr_swinton.engines.slice import get_slice

    from .helpers import format_json, parse_entry

    language = task.get("language", "python")
    fmt = task.get("context_format", "json")
    direction = task.get("slice_direction", "backward")
    line = task.get("slice_line")
    variable = task.get("slice_variable")

    if not line:
        raise ValueError("task.slice_line is required for slice variant")

    file_path, func_name = parse_entry(task)

    lines = sorted(get_slice(str(file_path), func_name, line, direction=direction, variable=variable, language=language))
    payload = {
        "file": str(file_path),
        "function": func_name,
        "line": line,
        "direction": direction,
        "variable": variable,
        "slice_lines": lines,
    }
    return format_json(payload, fmt)
