from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Any

import tiktoken


def _resolve_encoding(model: str) -> tuple[str, tiktoken.Encoding]:
    normalized = (model or "").lower()
    model_name = normalized.split("/", 1)[-1]
    if model_name.startswith(("gpt-", "o1", "o3", "codex")):
        enc = tiktoken.encoding_for_model("gpt-4o")
        return "tiktoken:gpt-4o", enc
    enc = tiktoken.get_encoding("cl100k_base")
    return "tiktoken:cl100k_base", enc


def count_tokens(text: str, model: str | None = None) -> int:
    _tokenizer_id, enc = _resolve_encoding(model or "")
    return len(enc.encode(text or "", disallowed_special=()))


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


@dataclass
class ContextMetrics:
    context_bytes: int
    context_tokens: int
    compression_ratio: float
    budget_compliance: float
    symbols_included: int
    symbols_signature_only: int
    avg_code_tokens_per_symbol: float
    total_call_edges: int
    avg_calls_per_function: float
    max_calls_shown: int
    pct_symbol_body_included: float
    windows_per_symbol: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_bytes": self.context_bytes,
            "context_tokens": self.context_tokens,
            "compression_ratio": self.compression_ratio,
            "budget_compliance": self.budget_compliance,
            "symbols_included": self.symbols_included,
            "symbols_signature_only": self.symbols_signature_only,
            "avg_code_tokens_per_symbol": self.avg_code_tokens_per_symbol,
            "total_call_edges": self.total_call_edges,
            "avg_calls_per_function": self.avg_calls_per_function,
            "max_calls_shown": self.max_calls_shown,
            "pct_symbol_body_included": self.pct_symbol_body_included,
            "windows_per_symbol": self.windows_per_symbol,
        }


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _count_windows(code: str) -> int:
    if not code:
        return 0
    return code.splitlines().count("...") + 1


def calculate_context_metrics(
    output: str,
    budget: int | None = None,
    baseline: str | None = None,
    tokenizer_model: str | None = None,
) -> ContextMetrics:
    context_tokens = count_tokens(output, tokenizer_model)
    context_bytes = len(output.encode("utf-8"))

    compression_ratio = 1.0
    if baseline is not None:
        baseline_tokens = count_tokens(baseline, tokenizer_model)
        compression_ratio = baseline_tokens / max(1, context_tokens)

    budget_compliance = 1.0
    if budget:
        budget_compliance = _clamp(1.0 - abs(context_tokens - budget) / budget)

    symbols_included = 0
    symbols_signature_only = 0
    avg_code_tokens_per_symbol = 0.0
    pct_symbol_body_included = 0.0
    windows_per_symbol = 0.0

    total_call_edges = 0
    max_calls_shown = 0
    call_lines = 0

    try:
        data = json.loads(output)
    except Exception:
        data = None

    if isinstance(data, dict) and isinstance(data.get("slices"), list):
        slices = data.get("slices", [])
        symbols_included = len(slices)
        code_tokens_total = 0
        code_entries = 0
        window_total = 0
        body_ratio_total = 0.0
        body_ratio_count = 0

        for item in slices:
            code = item.get("code")
            lines_range = item.get("lines") or []
            if code:
                code_entries += 1
                code_tokens_total += count_tokens(code, tokenizer_model)
                window_total += _count_windows(code)
                if len(lines_range) == 2:
                    span = max(1, lines_range[1] - lines_range[0] + 1)
                    code_lines = [line for line in code.splitlines() if line != "..."]
                    body_ratio_total += len(code_lines) / span
                    body_ratio_count += 1
            else:
                symbols_signature_only += 1

        if code_entries:
            avg_code_tokens_per_symbol = code_tokens_total / code_entries
            windows_per_symbol = window_total / code_entries
        if body_ratio_count:
            pct_symbol_body_included = body_ratio_total / body_ratio_count

    # Text parsing for call metrics
    for line in output.splitlines():
        if "calls:" in line:
            prefix, tail = line.split("calls:", 1)
            calls_blob = tail.strip()
            more = 0
            if "(+" in calls_blob:
                try:
                    suffix = calls_blob.split("(+", 1)[1]
                    more = int(suffix.split(")", 1)[0])
                    calls_blob = calls_blob.split("(+", 1)[0].strip()
                except (ValueError, IndexError):
                    pass
            shown = 0
            if calls_blob:
                shown = len([c for c in (c.strip() for c in calls_blob.split(",")) if c])
            total_call_edges += shown + more
            max_calls_shown = max(max_calls_shown, shown)
            call_lines += 1

    avg_calls_per_function = 0.0
    if call_lines:
        avg_calls_per_function = total_call_edges / call_lines

    return ContextMetrics(
        context_bytes=context_bytes,
        context_tokens=context_tokens,
        compression_ratio=compression_ratio,
        budget_compliance=budget_compliance,
        symbols_included=symbols_included,
        symbols_signature_only=symbols_signature_only,
        avg_code_tokens_per_symbol=avg_code_tokens_per_symbol,
        total_call_edges=total_call_edges,
        avg_calls_per_function=avg_calls_per_function,
        max_calls_shown=max_calls_shown,
        pct_symbol_body_included=pct_symbol_body_included,
        windows_per_symbol=windows_per_symbol,
    )
