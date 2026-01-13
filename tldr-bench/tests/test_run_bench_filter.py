import os
import subprocess


def run_cmd(args):
    env = os.environ.copy()
    env["PYTHONPATH"] = "tldr-bench"
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_list_tasks_filter():
    result = run_cmd([
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        "tldr-bench/scripts/run_bench.py",
        "--tasks",
        "curated",
        "--list-tasks",
        "--filter",
        "cur-cli",
    ])
    assert result.returncode == 0
    assert "cur-cli-codex" in result.stdout
    assert "cur-cli-claude" in result.stdout
    assert "cur-001" not in result.stdout


def test_print_results_variant():
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
    ])
    assert result.returncode == 0
    assert "cur-001" in result.stdout
    assert "not_implemented" in result.stdout
