from __future__ import annotations

from pathlib import Path
from typing import Optional
import os


def resolve_bench_dir(root: Optional[Path] = None) -> Path:
    env_path = os.getenv("OH_BENCH_DIR")
    if env_path:
        bench = Path(env_path).expanduser()
        if bench.exists():
            return bench
        raise FileNotFoundError(f"OH_BENCH_DIR not found: {bench}")

    base = root if root is not None else Path(__file__).resolve().parents[1]
    candidate = base / "vendor" / "openhands-benchmarks"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"OpenHands benchmarks not found under {candidate}")
