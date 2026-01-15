VARIANT_ID = "baselines"


def build_context(task: dict) -> str:
    from pathlib import Path

    from . import resolve_project_root

    project = resolve_project_root(task)
    entry = task.get("entry", "")
    if not entry:
        raise ValueError("task.entry is required")

    path_token = entry.split(":", 1)[0]
    file_path = Path(path_token)
    if not file_path.is_absolute():
        file_path = project / file_path
    if not file_path.exists():
        raise FileNotFoundError(f"Baseline file not found: {file_path}")

    rel_path = file_path
    try:
        rel_path = file_path.relative_to(project)
    except ValueError:
        pass

    header = f"# File: {rel_path}"
    body = file_path.read_text(encoding="utf-8")
    return f"{header}\n\n{body}"
