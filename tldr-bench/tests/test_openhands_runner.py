import subprocess

from tldr_bench.runners.openhands_runner import run_task


def test_run_task_with_bench_command():
    task = {"id": "cur-echo", "bench_command": ["/bin/echo", "ok"]}
    result = run_task(task, "baselines")
    assert result["status"] == "completed"
    assert "ok" in (result.get("stdout") or "")


def test_run_task_passes_max_retries_and_workers(monkeypatch, tmp_path):
    captured = {}

    def fake_resolve_bench_dir():
        return tmp_path

    def fake_run(cmd, cwd, text, capture_output, check):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    import tldr_bench.runners.openhands_runner as openhands_runner

    monkeypatch.setattr(openhands_runner, "resolve_bench_dir", fake_resolve_bench_dir)
    monkeypatch.setattr(openhands_runner.subprocess, "run", fake_run)

    task = {
        "id": "exec-001",
        "benchmark": "swebench",
        "llm_config": "/tmp/llm_config_codex.json",
        "select": "django__django-11333",
        "max_iterations": 1,
        "num_workers": 1,
        "max_retries": 0,
    }
    result = run_task(task, "baselines")
    assert result["status"] == "completed"
    assert "--max-iterations" in captured["cmd"]
    assert "--num-workers" in captured["cmd"]
    assert "--max-retries" in captured["cmd"]
