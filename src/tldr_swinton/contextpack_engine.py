from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .symbol_registry import SymbolRegistry


@dataclass(frozen=True)
class Candidate:
    symbol_id: str
    relevance: int
    relevance_label: str | None = None
    order: int = 0
    signature: str | None = None
    code: str | None = None
    lines: tuple[int, int] | None = None
    meta: dict[str, object] | None = None


@dataclass
class ContextSlice:
    id: str
    signature: str
    code: str | None
    lines: tuple[int, int] | None
    relevance: str | None = None
    meta: dict[str, object] | None = None
    etag: str | None = None


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
        ordered = sorted(candidates, key=lambda c: (-c.relevance, c.order, c.symbol_id))
        slices: list[ContextSlice] = []
        signatures_only: list[str] = []
        used = 0

        for candidate in ordered:
            info = None
            if candidate.signature is None:
                if self._registry is None:
                    raise ValueError("ContextPackEngine requires a SymbolRegistry for missing signatures")
                info = self._registry.get(candidate.symbol_id)
            signature = candidate.signature or (info.signature if info else "")
            if candidate.code is None and self._registry is not None and info is None:
                info = self._registry.get(candidate.symbol_id)
            code = candidate.code if candidate.code is not None else (info.code if info else None)
            if candidate.lines is None and self._registry is not None and info is None:
                info = self._registry.get(candidate.symbol_id)
            lines = candidate.lines if candidate.lines is not None else (info.lines if info else None)

            sig_cost = _estimate_tokens(signature)
            full_cost = sig_cost
            if code:
                full_cost += _estimate_tokens(code)

            if budget_tokens is None or used + full_cost <= budget_tokens:
                etag = _compute_etag(signature, code)
                slices.append(
                    ContextSlice(
                        id=candidate.symbol_id,
                        signature=signature,
                        code=code,
                        lines=lines,
                        relevance=candidate.relevance_label,
                        meta=candidate.meta,
                        etag=etag,
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


def _compute_etag(signature: str, code: str | None) -> str:
    payload = signature
    if code:
        payload = f"{signature}\n{code}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
