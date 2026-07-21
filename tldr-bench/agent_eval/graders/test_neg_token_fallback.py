from __future__ import annotations

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core import token_utils  # noqa: E402


def fallback_string() -> None:
    token_utils._get_tiktoken_encoder = lambda: None
    assert token_utils.estimate_tokens("x" * 40) == 10


def fallback_empty() -> None:
    token_utils._get_tiktoken_encoder = lambda: None
    assert token_utils.estimate_tokens("") == 1


def fallback_iterable() -> None:
    token_utils._get_tiktoken_encoder = lambda: None
    assert token_utils.estimate_tokens(["abcd", "efgh"]) == 2


run(
    [
        ("four characters per token", fallback_string),
        ("empty input floor", fallback_empty),
        ("iterable input", fallback_iterable),
    ]
)
