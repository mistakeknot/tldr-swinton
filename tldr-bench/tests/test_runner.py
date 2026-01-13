from tldr_bench.runners.openhands_runner import run_task


def test_run_task_returns_placeholder():
    task = {"id": "cur-001"}
    result = run_task(task, "baselines")
    assert result["task_id"] == "cur-001"
    assert result["variant_id"] == "baselines"
    assert result["status"] == "not_implemented"
