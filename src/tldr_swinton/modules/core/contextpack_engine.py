from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path

from .import_compress import compress_imports_section
from .strip import strip_code
from .symbol_registry import SymbolRegistry
from .token_utils import estimate_tokens as _estimate_tokens
from .type_pruner import prune_expansion
from .zoom import ZoomLevel, format_at_zoom


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
    import_compression: dict | None = None


def _collect_import_compression(slices: list[ContextSlice]) -> dict | None:
    file_imports: dict[str, list[str]] = {}

    for item in slices:
        if not isinstance(item.meta, dict):
            continue
        raw_imports = item.meta.get("imports")
        if isinstance(raw_imports, str):
            imports = [raw_imports]
        elif isinstance(raw_imports, list):
            imports = [imp for imp in raw_imports if isinstance(imp, str) and imp]
        else:
            continue

        if not imports or ":" not in item.id:
            continue

        file_path = item.id.split(":", 1)[0]
        if not file_path:
            continue
        file_imports.setdefault(file_path, []).extend(imports)

    if not file_imports:
        return None

    common_header, per_file = compress_imports_section(file_imports)
    if not common_header and not any(per_file.values()):
        return None

    return {"common_header": common_header, "per_file": per_file}


class ContextPackEngine:
    def __init__(self, registry: SymbolRegistry | None = None) -> None:
        self._registry = registry

    def build_context_pack(
        self,
        candidates: list[Candidate],
        budget_tokens: int | None = None,
        post_processors: list[Callable[[list[Candidate]], list[Candidate]]] | None = None,
        zoom_level: ZoomLevel = ZoomLevel.L4,
        strip_comments: bool = False,
        compress_imports: bool = False,
        enable_type_pruning: bool = False,
    ) -> ContextPack:
        if not candidates:
            return ContextPack(slices=[])
        ordered = sorted(candidates, key=lambda c: (-c.relevance, c.order, c.symbol_id))
        if post_processors:
            for processor in post_processors:
                ordered = processor(ordered)
        if enable_type_pruning and ordered:
            ordered = prune_expansion(
                ordered,
                callee_signature=ordered[0].signature or "",
                callee_code=ordered[0].code,
            )
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
            if strip_comments and code:
                code = strip_code(code, _infer_language_from_symbol_id(candidate.symbol_id))
            if candidate.lines is None and self._registry is not None and info is None:
                info = self._registry.get(candidate.symbol_id)
            lines = candidate.lines if candidate.lines is not None else (info.lines if info else None)

            language = _infer_language_from_symbol_id(candidate.symbol_id)
            zoomed = format_at_zoom(
                candidate.symbol_id,
                signature,
                code,
                zoom_level,
                language=language,
            )
            if zoom_level in (ZoomLevel.L0, ZoomLevel.L1):
                effective_code = None
            elif zoom_level is ZoomLevel.L2:
                effective_code = _extract_zoom_code(zoomed, candidate.symbol_id, signature)
            else:
                effective_code = code

            sig_cost = _estimate_tokens(signature)
            full_cost = sig_cost
            if effective_code:
                full_cost += _estimate_tokens(effective_code)

            if budget_tokens is None or used + full_cost <= budget_tokens:
                etag = _compute_etag(signature, effective_code)
                slices.append(
                    ContextSlice(
                        id=candidate.symbol_id,
                        signature=signature,
                        code=effective_code,
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

        import_compression = _collect_import_compression(slices) if compress_imports else None

        return ContextPack(
            slices=slices,
            budget_used=used,
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": len(slices)},
            import_compression=import_compression,
        )

    def build_context_pack_delta(
        self,
        candidates: list[Candidate],
        delta_result: "DeltaResult",
        budget_tokens: int | None = None,
        post_processors: list[Callable[[list[Candidate]], list[Candidate]]] | None = None,
        zoom_level: ZoomLevel = ZoomLevel.L4,
        compress_imports: bool = False,
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
        if post_processors:
            for processor in post_processors:
                ordered = processor(ordered)
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

            language = _infer_language_from_symbol_id(candidate.symbol_id)
            zoomed = format_at_zoom(
                candidate.symbol_id,
                signature,
                code,
                zoom_level,
                language=language,
            )
            if zoom_level in (ZoomLevel.L0, ZoomLevel.L1):
                effective_code = None
            elif zoom_level is ZoomLevel.L2:
                effective_code = _extract_zoom_code(zoomed, candidate.symbol_id, signature)
            else:
                effective_code = code

            sig_cost = _estimate_tokens(signature)
            full_cost = sig_cost
            if effective_code:
                full_cost += _estimate_tokens(effective_code)

            etag = _compute_etag(signature, effective_code)

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
                            code=effective_code,
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

        import_compression = _collect_import_compression(slices) if compress_imports else None

        return ContextPack(
            slices=slices,
            budget_used=used,
            unchanged=unchanged_ids,
            rehydrate=delta_result.rehydrate if delta_result.rehydrate else None,
            cache_stats={"hit_rate": hit_rate, "hits": hits, "misses": misses},
            import_compression=import_compression,
        )


def _collect_symbol_bodies(
    project_root: Path,
    symbol_ids: list[str],
) -> dict[str, tuple[str, tuple[int, int]]]:
    from .hybrid_extractor import HybridExtractor

    file_to_symbols: dict[str, set[str]] = {}
    for symbol_id in symbol_ids:
        if ":" not in symbol_id:
            continue
        file_part, symbol_name = symbol_id.split(":", 1)
        if not file_part or not symbol_name:
            continue
        file_to_symbols.setdefault(file_part, set()).add(symbol_name)

    extractor = HybridExtractor()
    bodies: dict[str, tuple[str, tuple[int, int]]] = {}

    for file_part, symbol_names in file_to_symbols.items():
        file_path = project_root / file_part
        if not file_path.is_file():
            continue

        try:
            source = file_path.read_text()
        except OSError:
            continue

        src_lines = source.splitlines()
        if not src_lines:
            continue

        try:
            info = extractor.extract(str(file_path))
        except Exception:
            continue

        starts: dict[str, int] = {}

        def _register(name: str, line: int) -> None:
            if line <= 0:
                return
            if name not in starts or line < starts[name]:
                starts[name] = line

        for func in info.functions:
            _register(func.name, func.line_number)
        for cls in info.classes:
            _register(cls.name, cls.line_number)
            for method in cls.methods:
                _register(f"{cls.name}.{method.name}", method.line_number)

        if not starts:
            continue

        ordered = sorted(starts.items(), key=lambda item: item[1])
        ranges: dict[str, tuple[int, int]] = {}
        total = len(src_lines)

        for idx, (name, start_line) in enumerate(ordered):
            next_start = total + 1
            for _, candidate_start in ordered[idx + 1:]:
                if candidate_start > start_line:
                    next_start = candidate_start
                    break
            end_line = max(start_line, next_start - 1)
            ranges[name] = (start_line, end_line)

        for symbol_name in symbol_names:
            span = ranges.get(symbol_name)
            if span is None and "." in symbol_name:
                span = ranges.get(symbol_name.split(".")[-1])
            if span is None:
                continue

            start_line, end_line = span
            start_line = max(1, min(start_line, total))
            end_line = max(start_line, min(end_line, total))
            code = "\n".join(src_lines[start_line - 1:end_line]).rstrip()
            if not code:
                continue
            bodies[f"{file_part}:{symbol_name}"] = (code, (start_line, end_line))

    return bodies


def _apply_budget_to_dict_slices(slices: list[dict], budget_tokens: int) -> tuple[list[dict], int]:
    budgeted: list[dict] = []
    used = 0

    for item in slices:
        signature = item.get("signature", "") or ""
        code = item.get("code")
        sig_cost = _estimate_tokens(signature)
        full_cost = sig_cost + (_estimate_tokens(code) if code else 0)

        out = dict(item)
        if code and used + full_cost <= budget_tokens:
            used += full_cost
        elif used + sig_cost <= budget_tokens:
            out["code"] = None
            out["etag"] = _compute_etag(signature, None)
            used += sig_cost
        else:
            break
        budgeted.append(out)

    return budgeted, used


def _apply_budget_to_context_slices(
    slices: list[ContextSlice],
    budget_tokens: int,
) -> tuple[list[ContextSlice], int]:
    budgeted: list[ContextSlice] = []
    used = 0

    for item in slices:
        sig_cost = _estimate_tokens(item.signature)
        full_cost = sig_cost + (_estimate_tokens(item.code) if item.code else 0)

        if item.code and used + full_cost <= budget_tokens:
            budgeted.append(item)
            used += full_cost
        elif used + sig_cost <= budget_tokens:
            budgeted.append(replace(item, code=None, etag=_compute_etag(item.signature, None)))
            used += sig_cost
        else:
            break

    return budgeted, used


def include_symbol_bodies(
    pack: dict | ContextPack,
    project_root: str | Path,
    language: str = "python",
    budget_tokens: int | None = None,
    strip_comments: bool = False,
) -> dict | ContextPack:
    """Populate `code` in context slices for symbol IDs of the form `file:symbol`."""
    root = Path(project_root).resolve()

    if isinstance(pack, ContextPack):
        if not pack.slices:
            return pack

        symbol_ids = [item.id for item in pack.slices if item.id and item.code is None]
        bodies = _collect_symbol_bodies(root, symbol_ids)
        if not bodies:
            return pack

        enriched: list[ContextSlice] = []
        for item in pack.slices:
            body = bodies.get(item.id)
            if body and item.code is None:
                code, lines = body
                if strip_comments and code:
                    code = strip_code(code, language)
                enriched.append(
                    replace(
                        item,
                        code=code,
                        lines=lines,
                        etag=_compute_etag(item.signature, code),
                    )
                )
            else:
                enriched.append(item)

        if budget_tokens is not None:
            pack.slices, pack.budget_used = _apply_budget_to_context_slices(enriched, budget_tokens)
        else:
            pack.slices = enriched
            used = 0
            for item in pack.slices:
                used += _estimate_tokens(item.signature)
                if item.code:
                    used += _estimate_tokens(item.code)
            pack.budget_used = used
        return pack

    if not isinstance(pack, dict):
        return pack

    slices = pack.get("slices")
    if not isinstance(slices, list) or not slices:
        return pack

    symbol_ids: list[str] = []
    for item in slices:
        if not isinstance(item, dict):
            continue
        symbol_id = item.get("id")
        if isinstance(symbol_id, str) and symbol_id and item.get("code") is None:
            symbol_ids.append(symbol_id)

    bodies = _collect_symbol_bodies(root, symbol_ids)
    if not bodies:
        return pack

    enriched: list[dict] = []
    for item in slices:
        if not isinstance(item, dict):
            continue
        out = dict(item)
        symbol_id = out.get("id")
        body = bodies.get(symbol_id) if isinstance(symbol_id, str) else None
        if body and out.get("code") is None:
            code, lines = body
            if strip_comments and code:
                code = strip_code(code, language)
            signature = out.get("signature", "") or ""
            out["code"] = code
            out["lines"] = list(lines)
            out["etag"] = _compute_etag(signature, code)
        enriched.append(out)

    if budget_tokens is not None:
        budgeted, used = _apply_budget_to_dict_slices(enriched, budget_tokens)
    else:
        budgeted = enriched
        used = 0
        for item in budgeted:
            signature = item.get("signature", "") or ""
            used += _estimate_tokens(signature)
            code = item.get("code")
            if code:
                used += _estimate_tokens(code)

    out_pack = dict(pack)
    out_pack["slices"] = budgeted
    out_pack["budget_used"] = used
    return out_pack


def _compute_etag(signature: str, code: str | None) -> str:
    payload = signature
    if code:
        payload = f"{signature}\n{code}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_zoom_code(zoomed: str, symbol_id: str, signature: str) -> str | None:
    prefix = format_at_zoom(symbol_id, signature, None, ZoomLevel.L1)
    if not zoomed.startswith(prefix):
        return None
    body = zoomed[len(prefix):].lstrip("\n")
    return body or None


def _infer_language_from_symbol_id(symbol_id: str) -> str:
    file_part = symbol_id.split(":", 1)[0]
    if "." not in file_part:
        return "python"
    ext = Path(file_part).suffix.lower()
    if ext in {".py", ".pyi", ".pyx"}:
        return "python"
    if ext in {".ts", ".tsx"}:
        return "typescript"
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    if ext == ".go":
        return "go"
    if ext == ".rs":
        return "rust"
    return "python"
