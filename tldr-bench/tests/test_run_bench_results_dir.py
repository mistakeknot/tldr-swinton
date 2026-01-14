import os
import subprocess
from pathlib import Path


def test_results_dir_flag(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = "tldr-bench"
    result = subprocess.run(
        [
            "uv",
            "run",
            "--with",
            "pyyaml",
            "python",
            "tldr-bench/scripts/run_bench.py",
            "--tasks",
            "curated",
            "--variant",
            "baselines",
            "--filter",
            "cur-001",
            "--print-results",
            "--results-dir",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    output = list(Path(tmp_path).glob("*.jsonl"))
    assert output
    content = output[0].read_text(encoding="utf-8")
    assert "cur-001" in content
