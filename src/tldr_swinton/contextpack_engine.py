from __future__ import annotations

from dataclasses import dataclass

from .symbol_registry import SymbolRegistry


@dataclass(frozen=True)
class Candidate:
    symbol_id: str
    relevance: int


@dataclass
class ContextSlice:
    id: str
    signature: str
    code: str | None
    lines: tuple[int, int] | None
    relevance: str | None = None


@dataclass
class ContextPack:
    slices: list[ContextSlice]
    signatures_only: list[str]
    budget_used: int = 0


class ContextPackEngine:
    def __init__(self, registry: SymbolRegistry | None = None) -> None:
        self._registry = registry

    def build_context_pack(
        self,
        candidates: list[Candidate],
        budget_tokens: int | None = None,
    ) -> ContextPack:
        if not candidates:
            return ContextPack(slices=[], signatures_only=[])
        if self._registry is None:
            raise ValueError("ContextPackEngine requires a SymbolRegistry")

        ordered = sorted(candidates, key=lambda c: (-c.relevance, c.symbol_id))
        slices: list[ContextSlice] = []
        signatures_only: list[str] = []
        used = 0

        for candidate in ordered:
            info = self._registry.get(candidate.symbol_id)
            signature = info.signature
            code = info.code
            lines = info.lines

            sig_cost = _estimate_tokens(signature)
            full_cost = sig_cost
            if code:
                full_cost += _estimate_tokens(code)

            if budget_tokens is None or used + full_cost <= budget_tokens:
                slices.append(
                    ContextSlice(
                        id=candidate.symbol_id,
                        signature=signature,
                        code=code,
                        lines=lines,
                    )
                )
                used += full_cost
            elif used + sig_cost <= budget_tokens:
                signatures_only.append(candidate.symbol_id)
                used += sig_cost
            else:
                break

        return ContextPack(
            slices=slices,
            signatures_only=signatures_only,
            budget_used=used,
        )


def _estimate_tokens(text: str) -> int:
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        return max(1, len(text) // 4)
