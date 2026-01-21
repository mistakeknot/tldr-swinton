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
    budget_used: int = 0
    unchanged: list[str] | None = None  # Symbol IDs that were unchanged (delta mode)
    rehydrate: dict[str, str] | None = None  # symbol_id -> vhs_ref for rehydration
    cache_stats: dict | None = None  # hit_rate, hits, misses


class ContextPackEngine:
    def __init__(self, registry: SymbolRegistry | None = None) -> None:
        self._registry = registry

    def build_context_pack(
        self,
        candidates: list[Candidate],
        budget_tokens: int | None = None,
    ) -> ContextPack:
        if not candidates:
            return ContextPack(slices=[])
        ordered = sorted(candidates, key=lambda c: (-c.relevance, c.order, c.symbol_id))
        slices: list[ContextSlice] = []
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
                etag = _compute_etag(signature, None)
                slices.append(
                    ContextSlice(
                        id=candidate.symbol_id,
                        signature=signature,
                        code=None,
                        lines=lines,
                        relevance=candidate.relevance_label,
                        meta=candidate.meta,
                        etag=etag,
                    )
                )
                used += sig_cost
            else:
                break

        return ContextPack(
            slices=slices,
            budget_used=used,
        )

    def build_context_pack_delta(
        self,
        candidates: list[Candidate],
        delta_result: "DeltaResult",
        budget_tokens: int | None = None,
    ) -> ContextPack:
        """Build context pack with delta detection.

        Unchanged symbols get signature-only slices with code=None.
        Changed/new symbols get full code (budget permitting).

        Args:
            candidates: List of candidate symbols
            delta_result: Result from StateStore.check_delta()
            budget_tokens: Optional token budget

        Returns:
            ContextPack with unchanged list and rehydration manifest
        """
        from .state_store import DeltaResult  # Avoid circular import at module level

        if not candidates:
            return ContextPack(slices=[], unchanged=[], rehydrate={})

        ordered = sorted(candidates, key=lambda c: (-c.relevance, c.order, c.symbol_id))
        slices: list[ContextSlice] = []
        used = 0
        unchanged_ids: list[str] = []
        hits = 0
        misses = 0

        for candidate in ordered:
            is_unchanged = candidate.symbol_id in delta_result.unchanged

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

            etag = _compute_etag(signature, code)

            if is_unchanged:
                # Unchanged: signature-only slice, count as hit
                hits += 1
                unchanged_ids.append(candidate.symbol_id)

                if budget_tokens is None or used + sig_cost <= budget_tokens:
                    slices.append(
                        ContextSlice(
                            id=candidate.symbol_id,
                            signature=signature,
                            code=None,  # Omit code for unchanged
                            lines=lines,
                            relevance=candidate.relevance_label,
                            meta=candidate.meta,
                            etag=etag,
                        )
                    )
                    used += sig_cost
                else:
                    break
            else:
                # Changed or new: include full code if budget allows
                misses += 1

                if budget_tokens is None or used + full_cost <= budget_tokens:
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
                    slices.append(
                        ContextSlice(
                            id=candidate.symbol_id,
                            signature=signature,
                            code=None,
                            lines=lines,
                            relevance=candidate.relevance_label,
                            meta=candidate.meta,
                            etag=etag,
                        )
                    )
                    used += sig_cost
                else:
                    break

        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0

        return ContextPack(
            slices=slices,
            budget_used=used,
            unchanged=unchanged_ids,
            rehydrate=delta_result.rehydrate if delta_result.rehydrate else None,
            cache_stats={"hit_rate": hit_rate, "hits": hits, "misses": misses},
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
