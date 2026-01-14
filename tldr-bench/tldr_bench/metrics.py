from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

import tiktoken


def _resolve_encoding(model: str) -> tuple[str, tiktoken.Encoding]:
    normalized = (model or "").lower()
    if normalized.startswith(("gpt-", "o1", "o3", "codex")):
        enc = tiktoken.encoding_for_model("gpt-4o")
        return "tiktoken:gpt-4o", enc
    enc = tiktoken.get_encoding("cl100k_base")
    return "tiktoken:cl100k_base", enc


def count_tokens(text: str, model: str | None = None) -> int:
    _tokenizer_id, enc = _resolve_encoding(model or "")
    return len(enc.encode(text or ""))


@dataclass
class TokenTiming:
    _durations: dict[str, float] = field(default_factory=dict)

    def section(self, name: str):
        start = time.perf_counter()

        class _Section:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, exc_type, exc, tb):
                self._durations[name] = (time.perf_counter() - start) * 1000

        return _Section()

    def to_dict(self) -> dict[str, Any]:
        return {f"{name}_ms": int(ms) for name, ms in self._durations.items()}
