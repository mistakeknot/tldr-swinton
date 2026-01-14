from tldr_bench.runners import static_context_runner


class DummyVariant:
    def build_context(self, task: dict) -> str:
        return "hello world"


def test_static_context_runner_counts_tokens(monkeypatch):
    monkeypatch.setattr(static_context_runner, "get_variant", lambda variant: DummyVariant())
    task = {"id": "static-ctx", "entry": "tldr_swinton/api.py:get_relevant_context"}
    result = static_context_runner.run_static(task, variant="difflens", run_config={"tokenizer_model": "gpt-4o"})
    assert result["task_id"] == "static-ctx"
    assert result["status"] == "completed"
    assert result["context_bytes"] > 0
    assert result["context_tokens_estimate"] > 0
    assert result["context_ms"] >= 0
