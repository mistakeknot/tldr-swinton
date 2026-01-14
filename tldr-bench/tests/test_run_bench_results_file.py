import os
import subprocess
from pathlib import Path


def test_results_file_flag(tmp_path):
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
            "--results-file",
            str(tmp_path / "custom.jsonl"),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    assert (tmp_path / "custom.jsonl").exists()
    content = (tmp_path / "custom.jsonl").read_text(encoding="utf-8")
    assert "cur-001" in content
