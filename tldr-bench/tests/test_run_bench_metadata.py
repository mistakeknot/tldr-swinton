import os
import subprocess
from pathlib import Path


def test_metadata_fields_logged(tmp_path):
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
            "--run-id",
            "run-123",
            "--task-suite",
            "curated-v1",
            "--benchmark",
            "swebench",
            "--dataset",
            "SWE-bench_Verified",
            "--split",
            "test",
            "--instance-ids",
            "django__django-11333",
            "--workspace",
            "docker",
            "--max-iterations",
            "5",
            "--timeout-seconds",
            "120",
            "--tldrs-version",
            "0.2.0",
            "--shim-config",
            "shim.toml",
            "--seed",
            "42",
            "--prompt-budget",
            "4000",
            "--context-strategy",
            "difflens",
            "--daemon-enabled",
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
    assert "run-123" in content
    assert "curated-v1" in content
    assert "swebench" in content
    assert "SWE-bench_Verified" in content
    assert "django__django-11333" in content
    assert "difflens" in content
    assert "\"host_os\"" in content
    assert "\"host_arch\"" in content
