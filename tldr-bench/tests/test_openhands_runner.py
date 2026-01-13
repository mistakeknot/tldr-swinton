from tldr_bench.runners.openhands_runner import run_task


def test_run_task_with_bench_command():
    task = {"id": "cur-echo", "bench_command": ["/bin/echo", "ok"]}
    result = run_task(task, "baselines")
    assert result["status"] == "completed"
    assert "ok" in (result.get("stdout") or "")
