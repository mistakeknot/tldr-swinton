from __future__ import annotations

from dataclasses import dataclass


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
    def build_context_pack(
        self,
        candidates: list[Candidate],
        budget_tokens: int | None = None,
    ) -> ContextPack:
        if not candidates:
            return ContextPack(slices=[], signatures_only=[])
        top = sorted(candidates, key=lambda c: (-c.relevance, c.symbol_id))[0]
        slice_item = ContextSlice(id=top.symbol_id, signature="", code=None, lines=None)
        return ContextPack(slices=[slice_item], signatures_only=[])
