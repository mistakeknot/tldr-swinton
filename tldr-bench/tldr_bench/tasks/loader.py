from pathlib import Path
from typing import Any

import yaml


def resolve_task_file(name_or_path: str) -> Path:
    candidate = Path(name_or_path)
    if candidate.exists():
        return candidate
    if name_or_path == "curated":
        return Path(__file__).with_name("curated.yaml")
    if name_or_path == "public":
        return Path(__file__).with_name("public_subset.yaml")
    if name_or_path == "track_context":
        return Path(__file__).with_name("track_context.yaml")
    if name_or_path == "track_frontier":
        return Path(__file__).with_name("track_frontier.yaml")
    if name_or_path == "track_executable":
        return Path(__file__).with_name("track_executable.yaml")
    if name_or_path == "track_dataset":
        return Path(__file__).with_name("track_dataset.yaml")
    if name_or_path == "track_dataset_context":
        return Path(__file__).with_name("track_dataset_context.yaml")
    if name_or_path == "official_datasets":
        return Path(__file__).with_name("official_datasets.yaml")
    raise FileNotFoundError(f"Unknown task file: {name_or_path}")


def load_tasks(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not data:
        return []
    if not isinstance(data, list):
        raise ValueError("Task YAML must be a list")
    return data
