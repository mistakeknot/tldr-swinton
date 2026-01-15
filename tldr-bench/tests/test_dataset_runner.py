from tldr_bench.runners.dataset_runner import run_dataset


def test_dataset_runner_sample_dataset_counts_tokens():
    task = {
        "id": "dataset-sample",
        "runner": "dataset",
        "dataset_path": "data/swebench_sample.jsonl",
        "dataset_kind": "swebench",
    }
    result = run_dataset(task, variant="baselines", run_config={"tokenizer_model": "gpt-4o"})
    assert result["status"] == "completed"
    assert result["instances_total"] >= 2
    assert result["instances_selected"] >= 2
    assert result["prompt_tokens_total"] > 0
    assert result["prompt_tokens_median"] > 0
