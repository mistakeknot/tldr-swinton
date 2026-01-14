import os
import subprocess
from pathlib import Path


def test_cli_version_logged(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = "tldr-bench"
    env["TLDR_BENCH_RESULTS_DIR"] = str(tmp_path)
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
            "--cli-version",
            "codex-1.2.3",
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
    assert "codex-1.2.3" in content
