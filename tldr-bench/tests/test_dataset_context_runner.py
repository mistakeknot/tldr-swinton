from tldr_bench.runners.dataset_context_runner import run_dataset_context


class DummyVariant:
    def build_context(self, task: dict) -> str:
        return "context"


def test_dataset_context_runner_counts_tokens(monkeypatch):
    task = {
        "id": "dataset-ctx",
        "runner": "dataset_context",
        "dataset_path": "data/swebench_sample.jsonl",
        "dataset_kind": "swebench",
        "entry": "src/tldr_swinton/api.py:get_relevant_context",
    }
    monkeypatch.setattr(
        "tldr_bench.runners.dataset_context_runner.get_variant",
        lambda variant: DummyVariant(),
    )
    result = run_dataset_context(task, variant="baselines", run_config={"tokenizer_model": "gpt-4o"})
    assert result["status"] == "completed"
    assert result["context_tokens"] > 0
    assert result["prompt_tokens_total"] > 0
    assert result["total_tokens_total"] >= result["prompt_tokens_total"]
