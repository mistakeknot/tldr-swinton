from tldr_bench.runners import router


def test_router_selects_static_runner(monkeypatch):
    seen = {}

    def fake_run_static(task, variant, run_config):
        seen["task"] = task
        seen["variant"] = variant
        seen["run_config"] = run_config
        return {"task_id": task.get("id"), "status": "completed", "context_bytes": 1}

    monkeypatch.setattr(router, "run_static", fake_run_static)

    task = {"id": "static-1", "runner": "static"}
    result = router.run_task(task, variant="baselines", run_config={"tokenizer_model": "gpt-4o"})

    assert result["task_id"] == "static-1"
    assert result["status"] == "completed"
    assert result["context_bytes"] == 1
    assert seen["run_config"]["tokenizer_model"] == "gpt-4o"
