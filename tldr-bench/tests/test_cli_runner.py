from tldr_bench.runners.cli_runner import run_cli_task


def test_cli_runner_attaches_usage(tmp_path):
    log_path = tmp_path / "shim.jsonl"
    log_path.write_text('{"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}\n')
    task = {"id": "cli-1", "bench_command": ["echo", "ok"], "runner": "cli"}
    result = run_cli_task(task, variant="baselines", run_config={"shim_log_path": str(log_path)})
    assert result["prompt_tokens"] == 10
    assert result["completion_tokens"] == 5
