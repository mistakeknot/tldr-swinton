from dataclasses import dataclass
from pathlib import Path


@dataclass
class BenchConfig:
    root: Path
    results_dir: Path
