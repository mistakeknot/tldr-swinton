from tldr_bench.metrics import TokenTiming, count_tokens


def test_count_tokens_known_model():
    text = "hello world"
    result = count_tokens(text, model="gpt-4o")
    assert isinstance(result, int)
    assert result > 0


def test_token_timing_records_ms():
    timing = TokenTiming()
    with timing.section("context"):
        _ = "a" * 10
    data = timing.to_dict()
    assert "context_ms" in data
    assert data["context_ms"] >= 0
