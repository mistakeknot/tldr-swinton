"""Variant definitions for context strategies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import baselines, cassette, coveragelens, symbolkite
from . import cfg, dfg, difflens, pdg, slice
from . import edit_locality

# Disabled variants (moved to disabled/ - require different benchmark types):
# - attention_pruning: needs multi-session learning benchmark
# - context_delegation: needs agent execution benchmark
# - coherence_verify: needs error detection rate benchmark

VARIANTS = {
    "baselines": baselines,
    "symbolkite": symbolkite,
    "cassette": cassette,
    "coveragelens": coveragelens,
    "difflens": difflens,
    "dfg": dfg,
    "cfg": cfg,
    "pdg": pdg,
    "slice": slice,
    # Active efficiency features
    "edit_locality": edit_locality,
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
