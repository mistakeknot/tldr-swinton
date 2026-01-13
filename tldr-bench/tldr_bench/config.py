from dataclasses import dataclass
from pathlib import Path


@dataclass
class BenchConfig:
    root: Path
    results_dir: Path


OPENHANDS_BENCH_DIR_ENV = "OH_BENCH_DIR"
