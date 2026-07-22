from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


_SOURCE_FIELDS = {"id", "repository", "revision", "language", "license"}
_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class SourceSpec:
    id: str
    repository: str
    revision: str
    language: str
    license: str


def load_source_specs(path: Path) -> tuple[SourceSpec, ...]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or set(raw) != {"sources"}:
        raise ValueError("source manifest must contain only a sources list")
    items = raw["sources"]
    if not isinstance(items, list) or not items:
        raise ValueError("source manifest requires at least one source")

    specs: list[SourceSpec] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != _SOURCE_FIELDS:
            raise ValueError(f"source entries require: {sorted(_SOURCE_FIELDS)}")
        values: dict[str, Any] = item
        if not all(isinstance(values[field], str) and values[field] for field in _SOURCE_FIELDS):
            raise ValueError("source fields must be non-empty strings")
        if not _SOURCE_ID.fullmatch(values["id"]):
            raise ValueError(f"invalid source id: {values['id']}")
        if not _GIT_SHA.fullmatch(values["revision"]):
            raise ValueError(f"source revision must be a full Git SHA: {values['id']}")
        specs.append(SourceSpec(**values))

    ids = [spec.id for spec in specs]
    if len(set(ids)) != len(ids):
        raise ValueError("source ids must be unique")
    return tuple(specs)


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _require_clean(repo: Path) -> None:
    if _run_git(repo, "status", "--porcelain"):
        raise ValueError(f"source checkout is dirty: {repo}")


def prepare_sources(
    specs: tuple[SourceSpec, ...], output_dir: Path
) -> dict[str, Path]:
    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    prepared: dict[str, Path] = {}
    for spec in specs:
        destination = root / spec.id
        if destination.exists():
            if not (destination / ".git").exists():
                raise ValueError(f"source destination is not a Git checkout: {destination}")
            _require_clean(destination)
            remote = _run_git(destination, "remote", "get-url", "origin")
            if remote != spec.repository:
                raise ValueError(
                    f"source origin mismatch for {spec.id}: {remote} != {spec.repository}"
                )
        else:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    "--no-tags",
                    spec.repository,
                    str(destination),
                ],
                check=True,
                text=True,
                capture_output=True,
            )

        if _run_git(destination, "rev-parse", "HEAD") != spec.revision:
            subprocess.run(
                ["git", "fetch", "--depth", "1", "origin", spec.revision],
                cwd=destination,
                check=True,
                text=True,
                capture_output=True,
            )
        subprocess.run(
            ["git", "checkout", "--detach", spec.revision],
            cwd=destination,
            check=True,
            text=True,
            capture_output=True,
        )
        _require_clean(destination)
        actual = _run_git(destination, "rev-parse", "HEAD")
        if actual != spec.revision:
            raise ValueError(
                f"source revision mismatch for {spec.id}: {actual} != {spec.revision}"
            )
        prepared[spec.id] = destination.resolve()
    return prepared
