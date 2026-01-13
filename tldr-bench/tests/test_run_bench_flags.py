import os
import subprocess
import sys


def test_list_tasks_dry_run():
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
            "--list-tasks",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    assert "cur-001" in result.stdout
