import os
import subprocess
from pathlib import Path


def run_cmd(args, env):
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_print_results_writes_jsonl(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = "tldr-bench"
    env["TLDR_BENCH_RESULTS_DIR"] = str(tmp_path)
    result = run_cmd([
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
    ], env)
    assert result.returncode == 0
    output = list(Path(tmp_path).glob("*.jsonl"))
    assert output, "Expected JSONL log file"
    content = output[0].read_text(encoding="utf-8")
    assert "cur-001" in content
