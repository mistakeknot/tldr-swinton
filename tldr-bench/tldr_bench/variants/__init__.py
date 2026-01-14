"""Variant definitions for context strategies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import baselines, cassette, coveragelens, difflens, symbolkite

VARIANTS = {
    "baselines": baselines,
    "difflens": difflens,
    "symbolkite": symbolkite,
    "cassette": cassette,
    "coveragelens": coveragelens,
}


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


def get_variant(name: str):
    if name in VARIANTS:
        return VARIANTS[name]
    raise ValueError(f"Unknown variant: {name}")
