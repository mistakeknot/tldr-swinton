"""Variant definitions for context strategies."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_project_root(task: dict[str, Any]) -> Path:
    """Resolve project root for a task."""
    repo = task.get("project") or task.get("repo")
    if repo:
        repo_path = Path(str(repo))
        if repo_path.exists():
            return repo_path.resolve()

    root = Path(__file__).resolve().parents[3]
    if repo and root.name == str(repo):
        return root

    if repo and (root / str(repo)).exists():
        return (root / str(repo)).resolve()

    return root
