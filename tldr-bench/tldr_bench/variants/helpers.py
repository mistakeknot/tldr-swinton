from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import resolve_project_root


def parse_entry(task: dict) -> tuple[Path, str]:
    entry = task.get("entry", "")
    if not entry or ":" not in entry:
        raise ValueError("task.entry must be in path:function format")
    path_token, func_name = entry.split(":", 1)
    project = resolve_project_root(task)
    file_path = Path(path_token)
    if not file_path.is_absolute():
        file_path = project / file_path
    return file_path, func_name


def format_json(data: Any, fmt: str) -> str:
    if fmt == "json-pretty":
        return json.dumps(data, indent=2, ensure_ascii=False)
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
