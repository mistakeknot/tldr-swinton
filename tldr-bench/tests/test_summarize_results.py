from pathlib import Path

from tldr_bench.summary import summarize_jsonl


def test_summary_median_tokens(tmp_path):
    data = tmp_path / "run.jsonl"
    data.write_text('{"total_tokens": 10, "context_ms": 5}\n{"total_tokens": 20, "context_ms": 7}\n')
    summary = summarize_jsonl(Path(data))
    assert summary["total_tokens_median"] == 15
    assert summary["context_ms_median"] == 6
