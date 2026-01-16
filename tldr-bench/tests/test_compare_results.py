from pathlib import Path

from tldr_bench.compare_results import compare_results


def test_compare_results_sums_and_saves(tmp_path: Path):
    baseline = tmp_path / "baseline.jsonl"
    variant = tmp_path / "variant.jsonl"

    baseline.write_text(
        '{"task_id":"t1","context_tokens":10,"total_tokens_total":100}\n'
        '{"task_id":"t2","context_tokens":20,"total_tokens_total":200}\n',
        encoding="utf-8",
    )
    variant.write_text(
        '{"task_id":"t1","context_tokens":5,"total_tokens_total":60}\n'
        '{"task_id":"t2","context_tokens":10,"total_tokens_total":120}\n',
        encoding="utf-8",
    )

    results = compare_results(baseline, [variant])
    assert results[0]["tasks"] == 2
    assert results[0]["metrics"]["context_tokens"]["baseline"] == 30
    assert results[0]["metrics"]["context_tokens"]["variant"] == 15
    assert results[0]["metrics"]["total_tokens_total"]["baseline"] == 300
    assert results[0]["metrics"]["total_tokens_total"]["variant"] == 180


def test_compare_results_handles_totals(tmp_path: Path):
    baseline = tmp_path / "baseline.jsonl"
    variant = tmp_path / "variant.jsonl"
    baseline.write_text(
        '{"task_id":"t1","context_tokens":10,"total_tokens_total":100}\n',
        encoding="utf-8",
    )
    variant.write_text(
        '{"task_id":"t1","context_tokens":5,"total_tokens_total":60}\n',
        encoding="utf-8",
    )

    results = compare_results(baseline, [variant])
    assert results[0]["metrics"]["total_tokens_total"]["savings"] == 40
