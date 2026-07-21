from __future__ import annotations

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core.output_formats import truncate_output  # noqa: E402


def incomplete_first_symbol_is_removed() -> None:
    text = "\n".join(
        [
            "📍 src/example.py:long_function",
            "   line one",
            "   line two",
            "   line three",
            "   line four",
        ]
    )
    result = truncate_output(text, max_lines=3)
    assert "📍" not in result
    assert "line one" not in result
    assert "[TRUNCATED:" in result


def complete_prefix_is_preserved() -> None:
    text = "header\n\n📍 first\nbody\n\n📍 second\nbody"
    result = truncate_output(text, max_lines=6)
    assert "header" in result
    assert "📍 first" in result
    assert "📍 second" not in result
    assert "[TRUNCATED:" in result


run(
    [
        ("incomplete first symbol", incomplete_first_symbol_is_removed),
        ("complete prefix", complete_prefix_is_preserved),
    ]
)
