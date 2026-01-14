import os
import subprocess
from pathlib import Path


def test_model_alias_and_resolved_logged(tmp_path):
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
            "--model-alias",
            "sonnet",
            "--resolved-model",
            "claude-sonnet-4-20250514",
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
    assert "sonnet" in content
    assert "claude-sonnet-4-20250514" in content
