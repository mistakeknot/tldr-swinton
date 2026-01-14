from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def resolve_results_dir() -> Path:
    override = os.getenv("TLDR_BENCH_RESULTS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "results"


def default_results_path(prefix: str = "run-") -> Path:
    results_dir = resolve_results_dir()
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return results_dir / f"{prefix}{timestamp}.jsonl"
