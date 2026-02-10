from __future__ import annotations

from typing import Iterable


_TIKTOKEN_ENCODER = None


def _get_tiktoken_encoder():
    """Get cached tiktoken encoder to avoid repeated initialization."""
    global _TIKTOKEN_ENCODER
    if _TIKTOKEN_ENCODER is None:
        try:
            import tiktoken
            _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception:
            pass
    return _TIKTOKEN_ENCODER


def estimate_tokens(text_or_lines: str | Iterable[str]) -> int:
    if isinstance(text_or_lines, str):
        text = text_or_lines
    else:
        text = "\n".join(text_or_lines)

    encoder = _get_tiktoken_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)
