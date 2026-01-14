from tldr_swinton.output_formats import _estimate_tokens, _apply_budget


def test_estimate_tokens_monotonic() -> None:
    short = _estimate_tokens("hello")
    long = _estimate_tokens("hello world " * 10)
    assert long > short


def test_estimate_tokens_does_not_count_per_char() -> None:
    per_char = _estimate_tokens("h") * 5
    whole = _estimate_tokens("hello")
    assert whole < per_char


def test_apply_budget_stops_on_token_limit() -> None:
    lines = ["alpha " * 20, "beta " * 20]
    limited = _apply_budget(lines, budget_tokens=5)
    assert limited[-1].startswith("... (budget reached)")
