from types import SimpleNamespace

from tldr_bench.runners import cli_runner


def test_cli_runner_attaches_usage(tmp_path):
    log_path = tmp_path / "shim.jsonl"
    log_path.write_text('{"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}\n')
    task = {"id": "cli-1", "bench_command": ["echo", "ok"], "runner": "cli"}
    result = cli_runner.run_cli_task(task, variant="baselines", run_config={"shim_log_path": str(log_path)})
    assert result["prompt_tokens"] == 10
    assert result["completion_tokens"] == 5


def test_cli_runner_parses_tokens_from_output(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="tokens used\n27,064\n")

    monkeypatch.setattr(cli_runner.subprocess, "run", fake_run)
    task = {"id": "cli-2", "bench_command": ["codex", "exec", "hi"], "runner": "cli"}
    result = cli_runner.run_cli_task(task, variant="baselines", run_config={})
    assert result["total_tokens"] == 27064
