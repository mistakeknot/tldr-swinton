"""Context output formatting helpers."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Iterable

# Default max calls shown (for ultracompact format)
MAX_CALLS_DEFAULT = 12
# Minimum calls to always show
MAX_CALLS_MIN = 3
# Maximum calls when budget is high
MAX_CALLS_MAX = 20


def compute_max_calls(budget_tokens: int | None = None) -> int:
    """Compute token-aware max calls to display.

    Lower budgets get fewer call references to save tokens.
    Higher budgets can show more context.

    Args:
        budget_tokens: Optional token budget

    Returns:
        Max number of calls to display per function
    """
    if budget_tokens is None:
        return MAX_CALLS_DEFAULT

    if budget_tokens < 1000:
        return MAX_CALLS_MIN
    elif budget_tokens < 2000:
        return 5
    elif budget_tokens < 3000:
        return 8
    elif budget_tokens < 5000:
        return MAX_CALLS_DEFAULT
    else:
        return MAX_CALLS_MAX


# Backwards compatibility
MAX_CALLS = MAX_CALLS_DEFAULT


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped

from .api import RelevantContext
from .contextpack_engine import ContextPack, ContextSlice
from .json_codec import ALIASES, elide_nulls, pack_json, to_columnar
from .token_utils import estimate_tokens as _estimate_tokens


def format_context(
    ctx: RelevantContext,
    fmt: str = "text",
    budget_tokens: int | None = None,
) -> str:
    """Format RelevantContext for output.

    Args:
        ctx: RelevantContext instance
        fmt: "text", "ultracompact", or "cache-friendly"
        budget_tokens: Optional token budget (approximate, len/4)
    """
    # Handle cache-friendly by converting to pack-like structure
    if fmt == "cache-friendly":
        pack = {
            "slices": [
                {
                    "id": func.name,
                    "signature": func.signature,
                    "code": None,
                    "lines": [func.line, func.line] if func.line else None,
                    "relevance": f"depth_{func.depth}",
                }
                for func in ctx.functions
            ],
            "unchanged": None,  # Non-delta: no unchanged info
            "cache_stats": {
                "hit_rate": 0.0,
                "hits": 0,
                "misses": len(ctx.functions),
            },
        }
        return _format_cache_friendly(pack)

    if budget_tokens is None:
        if fmt == "text":
            return ctx.to_llm_string()
        if fmt == "ultracompact":
            # Even without budget, pass None for consistent behavior
            return "\n".join(_format_ultracompact(ctx, budget_tokens=None))
        raise ValueError(f"Unknown format: {fmt}")

    if fmt == "text":
        return _format_text_budgeted(ctx, budget_tokens)
    if fmt == "ultracompact":
        return _format_ultracompact_budgeted(ctx, budget_tokens)
    raise ValueError(f"Unknown format: {fmt}")


def _contextpack_to_dict(pack: ContextPack) -> dict:
    slices: list[dict] = []
    for item in pack.slices:
        slice_dict = {
            "id": item.id,
            "signature": item.signature,
            "code": item.code,
            "lines": list(item.lines) if item.lines else None,
            "relevance": item.relevance,
            "meta": item.meta,
            "etag": item.etag[:16] if item.etag else item.etag,
        }
        if isinstance(item.meta, dict) and item.meta.get("representation") == "incremental" and item.code is not None:
            slice_dict["diff"] = item.code
        slices.append(slice_dict)

    result = {
        "budget_used": pack.budget_used,
        "slices": slices,
    }
    # Include delta-specific fields if present (use `is not None` to preserve
    # the distinction between None=non-delta and []=delta-all-changed)
    if pack.unchanged is not None:
        result["unchanged"] = pack.unchanged
    if pack.rehydrate is not None:
        result["rehydrate"] = pack.rehydrate
    if pack.cache_stats is not None:
        result["cache_stats"] = pack.cache_stats
    if pack.import_compression is not None:
        result["import_compression"] = pack.import_compression
    return result


def _pack_symbol_id(
    symbol_id: str,
    path_refs: dict[str, str],
    path_dict: dict[str, str],
) -> str:
    if not isinstance(symbol_id, str) or ":" not in symbol_id:
        return symbol_id
    file_part, symbol = symbol_id.split(":", 1)
    if not file_part:
        return symbol_id
    ref = path_refs.get(file_part)
    if ref is None:
        ref = f"P{len(path_refs)}"
        path_refs[file_part] = ref
        path_dict[ref] = file_part
    return f"{ref}:{symbol}"


def _format_packed_json(pack: dict | ContextPack) -> str:
    pack_dict = _contextpack_to_dict(pack) if isinstance(pack, ContextPack) else copy.deepcopy(pack)
    if not isinstance(pack_dict, dict):
        return json.dumps(pack_dict, separators=(",", ":"), ensure_ascii=False)

    path_refs: dict[str, str] = {}
    path_dict: dict[str, str] = {}

    slices = pack_dict.get("slices")
    if isinstance(slices, list):
        for item in slices:
            if isinstance(item, dict) and item.get("id"):
                item["id"] = _pack_symbol_id(item["id"], path_refs, path_dict)

    unchanged = pack_dict.get("unchanged")
    if isinstance(unchanged, list):
        pack_dict["unchanged"] = [
            _pack_symbol_id(symbol_id, path_refs, path_dict)
            if isinstance(symbol_id, str)
            else symbol_id
            for symbol_id in unchanged
        ]

    rehydrate = pack_dict.get("rehydrate")
    if isinstance(rehydrate, dict):
        pack_dict["rehydrate"] = {
            _pack_symbol_id(symbol_id, path_refs, path_dict)
            if isinstance(symbol_id, str)
            else symbol_id: ref
            for symbol_id, ref in rehydrate.items()
        }

    packed = pack_json(elide_nulls(pack_dict))
    output = {"_aliases": ALIASES, "_paths": path_dict}
    if isinstance(packed, dict):
        output.update(packed)
    else:
        output["value"] = packed
    return json.dumps(output, separators=(",", ":"), ensure_ascii=False)


def _format_columnar_json(pack: dict | ContextPack) -> str:
    pack_dict = _contextpack_to_dict(pack) if isinstance(pack, ContextPack) else copy.deepcopy(pack)
    if not isinstance(pack_dict, dict):
        return json.dumps(pack_dict, separators=(",", ":"), ensure_ascii=False)

    slices = pack_dict.get("slices")
    path_refs: dict[str, str] = {}
    path_dict: dict[str, str] = {}
    if isinstance(slices, list):
        for item in slices:
            if not isinstance(item, dict):
                continue
            if item.get("id"):
                item["id"] = _pack_symbol_id(item["id"], path_refs, path_dict)
            meta = item.get("meta")
            if isinstance(meta, dict) and isinstance(meta.get("file"), str):
                file_ref = path_refs.get(meta["file"])
                if file_ref is None:
                    file_ref = f"P{len(path_refs)}"
                    path_refs[meta["file"]] = file_ref
                    path_dict[file_ref] = meta["file"]
                meta["file"] = file_ref

    unchanged = pack_dict.get("unchanged")
    if isinstance(unchanged, list):
        pack_dict["unchanged"] = [
            _pack_symbol_id(symbol_id, path_refs, path_dict)
            if isinstance(symbol_id, str)
            else symbol_id
            for symbol_id in unchanged
        ]

    rehydrate = pack_dict.get("rehydrate")
    if isinstance(rehydrate, dict):
        pack_dict["rehydrate"] = {
            _pack_symbol_id(symbol_id, path_refs, path_dict)
            if isinstance(symbol_id, str)
            else symbol_id: ref
            for symbol_id, ref in rehydrate.items()
        }

    slice_dicts = [item for item in slices if isinstance(item, dict)] if isinstance(slices, list) else []
    columnar_slices = to_columnar(slice_dicts)
    output = {key: value for key, value in pack_dict.items() if key != "slices"}
    output["_schema"] = list(columnar_slices.keys())
    output["_paths"] = path_dict
    output["slices"] = columnar_slices
    return json.dumps(output, separators=(",", ":"), ensure_ascii=False)


def format_context_pack(pack: dict | ContextPack, fmt: str = "ultracompact") -> str:
    """Format a DiffLens-style ContextPack."""
    # Handle legacy string "UNCHANGED" (for backwards compatibility)
    if pack == "UNCHANGED":
        pack = {"unchanged": True, "budget_used": 0, "slices": []}

    if isinstance(pack, ContextPack):
        pack = _contextpack_to_dict(pack)

    # Handle structured unchanged response
    if isinstance(pack, dict) and pack.get("unchanged") is True and not pack.get("slices"):
        if fmt == "packed-json":
            return _format_packed_json(pack)
        if fmt == "columnar-json":
            return _format_columnar_json(pack)
        if fmt in ("json", "json-pretty"):
            return json.dumps(pack, indent=2 if fmt == "json-pretty" else None, ensure_ascii=False)
        return "# UNCHANGED (no changes since last request)"
    # Handle error responses (including ambiguous)
    if isinstance(pack, dict) and pack.get("error") is True:
        if fmt == "packed-json":
            return _format_packed_json(pack)
        if fmt == "columnar-json":
            return _format_columnar_json(pack)
        if fmt in ("json", "json-pretty"):
            return json.dumps(pack, indent=2 if fmt == "json-pretty" else None, ensure_ascii=False)
        # Text format for errors
        message = pack.get("message", "Unknown error")
        candidates = pack.get("candidates", [])
        if candidates:
            lines = [message, "Candidates:"]
            for cand in candidates:
                lines.append(f"- {cand}")
            return "\n".join(lines)
        return message
    # Handle legacy ambiguous format (for backwards compatibility)
    if isinstance(pack, dict) and pack.get("ambiguous"):
        from .errors import ERR_AMBIGUOUS
        candidates = pack.get("candidates", [])
        structured = {
            "error": True,
            "code": ERR_AMBIGUOUS,
            "message": "Ambiguous entry point. Please specify one of the candidates.",
            "candidates": candidates,
            "slices": [],
        }
        if fmt == "packed-json":
            return _format_packed_json(structured)
        if fmt == "columnar-json":
            return _format_columnar_json(structured)
        if fmt in ("json", "json-pretty"):
            return json.dumps(structured, indent=2 if fmt == "json-pretty" else None, ensure_ascii=False)
        # Text format
        lines = ["Ambiguous entry point. Candidates:"]
        for cand in candidates:
            lines.append(f"- {cand}")
        return "\n".join(lines)
    if fmt == "json":
        return json.dumps(pack, separators=(",", ":"), ensure_ascii=False)
    if fmt == "json-pretty":
        return json.dumps(pack, indent=2, ensure_ascii=False)
    if fmt == "packed-json":
        return _format_packed_json(pack)
    if fmt == "columnar-json":
        return _format_columnar_json(pack)
    if fmt == "ultracompact":
        return "\n".join(_format_context_pack_ultracompact(pack))
    if fmt == "cache-friendly":
        return _format_cache_friendly(pack)
    raise ValueError(f"Unknown format: {fmt}")


def _apply_budget(lines: Iterable[str], budget_tokens: int) -> list[str]:
    used = 0
    output: list[str] = []
    for line in lines:
        est = _estimate_tokens(line)
        if used + est > budget_tokens:
            output.append("... (budget reached)")
            break
        output.append(line)
        used += est
    return output


def _render_text_function(ctx: RelevantContext, func, include_details: bool) -> list[str]:
    from pathlib import Path

    lines: list[str] = []
    indent = "  " * min(func.depth, ctx.depth)
    short_file = Path(func.file).name if func.file else "?"
    lines.append(f"{indent}📍 {func.name} ({short_file}:{func.line})")
    lines.append(f"{indent}   {func.signature}")

    if include_details:
        if func.docstring:
            doc = func.docstring.split("\n")[0][:80]
            lines.append(f"{indent}   # {doc}")
        if func.blocks is not None:
            complexity_marker = "🔥" if func.cyclomatic and func.cyclomatic > 10 else ""
            lines.append(
                f"{indent}   ⚡ complexity: {func.cyclomatic or '?'} ({func.blocks} blocks) {complexity_marker}"
            )
        if func.calls:
            calls_str = ", ".join(func.calls[:5])
            if len(func.calls) > 5:
                calls_str += f" (+{len(func.calls) - 5} more)"
            lines.append(f"{indent}   → calls: {calls_str}")

    lines.append("")
    return lines


def _format_text_budgeted(ctx: RelevantContext, budget_tokens: int) -> str:
    lines: list[str] = [f"## Code Context: {ctx.entry_point} (depth={ctx.depth})", ""]
    used = _estimate_tokens(lines)

    funcs = sorted(
        enumerate(ctx.functions),
        key=lambda pair: (pair[1].depth, pair[0]),
    )

    for _, func in funcs:
        full = _render_text_function(ctx, func, include_details=True)
        sig = _render_text_function(ctx, func, include_details=False)

        full_cost = _estimate_tokens(full)
        sig_cost = _estimate_tokens(sig)

        if used + full_cost <= budget_tokens:
            lines.extend(full)
            used += full_cost
        elif used + sig_cost <= budget_tokens:
            lines.extend(sig)
            used += sig_cost
        else:
            lines.append("... (budget reached)")
            break

    return "\n".join(lines)


def _split_symbol(name: str, file_path: str) -> tuple[str, str]:
    if ":" in name:
        file_part, sym = name.split(":", 1)
        return file_part, sym
    if file_path and file_path != "?":
        return file_path, name
    return "?", name


def _format_symbol(name: str, file_path: str, path_ids: dict[str, str]) -> str:
    file_part, sym = _split_symbol(name, file_path)
    pid = path_ids.setdefault(file_part, f"P{len(path_ids)}")
    return f"{pid}:{sym}"


def _format_symbol_inline(name: str, file_path: str) -> str:
    file_part, sym = _split_symbol(name, file_path)
    return f"{file_part}:{sym}"


def _format_ultracompact(
    ctx: RelevantContext,
    budget_tokens: int | None = None,
) -> list[str]:
    """Format context in ultracompact format.

    Args:
        ctx: RelevantContext to format
        budget_tokens: Optional token budget (affects max calls shown)
    """
    path_ids: dict[str, str] = {}
    lines: list[str] = []
    max_calls = compute_max_calls(budget_tokens)

    for func in ctx.functions:
        _format_symbol(func.name, func.file, path_ids)

        calls_list = _dedupe_preserve(func.calls)
        for callee in calls_list[:max_calls]:
            _format_symbol(callee, "", path_ids)

    if path_ids:
        header = " ".join([f"{pid}={path}" for path, pid in path_ids.items()])
        lines.append(header)
        lines.append("")

    for func in ctx.functions:
        display = _format_symbol(func.name, func.file, path_ids)
        signature = func.signature
        line_info = f" @{func.line}" if func.line else ""
        lines.append(f"{display} {signature}{line_info}")

        if func.calls:
            calls_list = _dedupe_preserve(func.calls)
            shown = calls_list[:max_calls]
            more = len(calls_list) - len(shown)
            calls = ", ".join(_format_symbol(c, "", path_ids) for c in shown)
            suffix = f" (+{more})" if more > 0 else ""
            lines.append(f"  calls: {calls}{suffix}")

    return lines


def _format_ultracompact_budgeted(ctx: RelevantContext, budget_tokens: int) -> str:
    path_ids: dict[str, str] = {}
    lines: list[str] = []
    used = 0
    max_calls = compute_max_calls(budget_tokens)

    funcs = sorted(
        enumerate(ctx.functions),
        key=lambda pair: (pair[1].depth, pair[0]),
    )

    def render_func(func, include_calls: bool, use_inline: bool = False) -> list[str]:
        func_lines: list[str] = []
        if use_inline:
            display = _format_symbol_inline(func.name, func.file)
        else:
            display = _format_symbol(func.name, func.file, path_ids)
        signature = func.signature
        line_info = f" @{func.line}" if func.line else ""
        func_lines.append(f"{display} {signature}{line_info}")
        if include_calls and func.calls:
            calls_list = _dedupe_preserve(func.calls)
            shown = calls_list[:max_calls]
            more = len(calls_list) - len(shown)
            if use_inline:
                calls = ", ".join(_format_symbol_inline(c, "") for c in shown)
            else:
                calls = ", ".join(_format_symbol(c, "", path_ids) for c in shown)
            suffix = f" (+{more})" if more > 0 else ""
            func_lines.append(f"  calls: {calls}{suffix}")
        return func_lines

    collected: list[str] = []

    for _, func in funcs:
        full = render_func(func, include_calls=True)
        sig = render_func(func, include_calls=False)

        full_cost = _estimate_tokens(full)
        sig_cost = _estimate_tokens(sig)

        if used + full_cost <= budget_tokens:
            collected.extend(full)
            used += full_cost
        elif used + sig_cost <= budget_tokens:
            collected.extend(sig)
            used += sig_cost
        else:
            collected.append("... (budget reached)")
            break

    if path_ids:
        header = " ".join([f"{pid}={path}" for path, pid in path_ids.items()])
        header_lines = [header, ""]
        header_cost = _estimate_tokens(header_lines)
        collected_cost = _estimate_tokens(collected)
        if header_cost + collected_cost <= budget_tokens:
            lines.extend(header_lines)
            lines.extend(collected)
            return "\n".join(lines)
        if collected_cost > budget_tokens:
            lines.extend(_apply_budget(collected, budget_tokens))
            return "\n".join(lines)

        # Header doesn't fit; re-render inline without path dictionary
        used = 0
        for _, func in funcs:
            full = render_func(func, include_calls=True, use_inline=True)
            sig = render_func(func, include_calls=False, use_inline=True)

            full_cost = _estimate_tokens(full)
            sig_cost = _estimate_tokens(sig)

            if used + full_cost <= budget_tokens:
                lines.extend(full)
                used += full_cost
            elif used + sig_cost <= budget_tokens:
                lines.extend(sig)
                used += sig_cost
            else:
                lines.append("... (budget reached)")
                break
        return "\n".join(lines)

    lines.extend(collected)
    return "\n".join(lines)


def _get_import_compression_meta(pack: dict) -> tuple[str, dict[str, str]]:
    import_meta = pack.get("import_compression")
    if not isinstance(import_meta, dict):
        return "", {}
    common_header = import_meta.get("common_header")
    per_file = import_meta.get("per_file")
    if not isinstance(common_header, str):
        common_header = ""
    if not isinstance(per_file, dict):
        return common_header, {}
    normalized: dict[str, str] = {}
    for file_path, value in per_file.items():
        if isinstance(file_path, str) and isinstance(value, str):
            normalized[file_path] = value
    return common_header, normalized


def _format_cache_friendly(pack: dict) -> str:
    """Format context pack for LLM provider prompt caching optimization.

    Layout (all content before CACHE_BREAKPOINT is the stable prefix):
    1. Header (no timestamps — they'd break byte-exact matching)
    2. Cache hints JSON metadata
    3. All symbol signatures sorted by symbol ID
    4. CACHE_BREAKPOINT marker
    5. Changed symbol code bodies sorted by symbol ID
    6. Stats footer

    Prefix maximization: ALL signatures go in the prefix, even for changed
    symbols. Signatures rarely change when only bodies are edited, so this
    gives 80-95% cache hit rates in typical edit sessions.

    Args:
        pack: ContextPack dict with slices, unchanged list, cache_stats.

    Returns:
        Formatted string with cache-friendly two-section layout.
    """
    slices = pack.get("slices", [])
    if not slices:
        return "# tldrs cache-friendly output\n\n# No symbols to display"
    common_header, per_file_imports = _get_import_compression_meta(pack)

    # --- Classify slices ---
    unchanged_val = pack.get("unchanged")
    if isinstance(unchanged_val, bool):
        unchanged_set: set[str] = set()
    elif unchanged_val is None:
        # Non-delta path: no unchanged info. All symbols with code
        # go to dynamic section (treat all as changed).
        unchanged_set = set()
    else:
        unchanged_set = set(unchanged_val)

    # Sort ALL slices deterministically by ID (contains file_path:symbol)
    all_slices = sorted(slices, key=lambda s: s.get("id", ""))

    # Identify changed symbols with code bodies for dynamic section
    dynamic_body_slices = [
        s for s in all_slices
        if s.get("code") is not None and s.get("id", "") not in unchanged_set
    ]

    # --- Build prefix section: ALL signatures ---
    prefix_parts: list[str] = [
        f"## CACHE PREFIX ({len(all_slices)} symbols)",
        "",
    ]
    seen_import_files: set[str] = set()

    for item in all_slices:
        symbol_id = item.get("id", "?")
        file_part, _ = _split_symbol(symbol_id, "")
        if file_part and file_part not in seen_import_files:
            seen_import_files.add(file_part)
            unique_imports = per_file_imports.get(file_part, "").strip()
            if unique_imports:
                prefix_parts.append(f"# Unique imports: {file_part}")
                for unique_line in unique_imports.splitlines():
                    prefix_parts.append(f"#   {unique_line}")

        signature = item.get("signature", "")
        lines_range = item.get("lines") or []
        line_info = ""
        if lines_range and len(lines_range) == 2:
            line_info = f" @{lines_range[0]}-{lines_range[1]}"
        relevance = item.get("relevance", "")
        unchanged_marker = " [UNCHANGED]" if symbol_id in unchanged_set else ""
        prefix_parts.append(
            f"{symbol_id} {signature}{line_info} [{relevance}]{unchanged_marker}".strip()
        )

    prefix_parts.append("")
    prefix_text = "\n".join(prefix_parts)
    prefix_for_metrics = (
        f"{common_header}\n\n{prefix_text}" if common_header else prefix_text
    )

    # --- Compute prefix metrics ---
    prefix_token_est = _estimate_tokens(prefix_for_metrics)
    prefix_hash = hashlib.sha256(prefix_for_metrics.encode("utf-8")).hexdigest()[:16]

    # --- Build dynamic section: code bodies only ---
    dynamic_parts: list[str] = []
    if dynamic_body_slices:
        dynamic_parts.append(f"## DYNAMIC CONTENT ({len(dynamic_body_slices)} changed symbols)")
        dynamic_parts.append("")
        for item in dynamic_body_slices:
            symbol_id = item.get("id", "?")
            signature = item.get("signature", "")
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
            representation = meta.get("representation")
            code = item.get("code", "")
            if representation == "incremental":
                dynamic_parts.extend(str(code).splitlines())
                dynamic_parts.append("")
                continue
            dynamic_parts.append(f"### {symbol_id}")
            dynamic_parts.append(f"{signature}")
            dynamic_parts.append("```")
            dynamic_parts.extend(code.splitlines())
            dynamic_parts.append("```")
            dynamic_parts.append("")

    dynamic_token_est = _estimate_tokens("\n".join(dynamic_parts)) if dynamic_parts else 0

    # --- Single-pass assembly with placeholder for hints ---
    header = "# tldrs cache-friendly output v1"
    breakpoint_line = f"<!-- CACHE_BREAKPOINT: ~{prefix_token_est} tokens -->"
    hints_placeholder = "__CACHE_HINTS_PLACEHOLDER__"

    final_parts: list[str] = [header, hints_placeholder, ""]
    if common_header:
        final_parts.extend(common_header.splitlines())
        final_parts.append("")
    final_parts.extend([prefix_text, breakpoint_line])
    if dynamic_parts:
        final_parts.append("")
        final_parts.extend(dynamic_parts)

    # Stats footer
    total_tokens = prefix_token_est + dynamic_token_est
    final_parts.append(
        f"## STATS: Prefix ~{prefix_token_est} tokens | Dynamic ~{dynamic_token_est} tokens | Total ~{total_tokens} tokens"
    )

    cache_stats = pack.get("cache_stats")
    if cache_stats:
        hit_rate = cache_stats.get("hit_rate", 0)
        hits = cache_stats.get("hits", 0)
        misses = cache_stats.get("misses", 0)
        final_parts.append(f"## Cache: {hits} unchanged, {misses} changed ({hit_rate:.0%} hit rate)")

    output = "\n".join(final_parts)

    # Compute breakpoint offset from assembled output, then replace placeholder
    breakpoint_offset = output.find("<!-- CACHE_BREAKPOINT")
    if breakpoint_offset < 0:
        breakpoint_offset = 0  # Defensive: degrade to 0 if marker missing
    hints_data = {
        "cache_hints": {
            "prefix_tokens": prefix_token_est,
            "prefix_hash": prefix_hash,
            "breakpoint_char_offset": breakpoint_offset,
            "format_version": 1,
        }
    }
    hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)
    output = output.replace(hints_placeholder, hints_line, 1)

    return output


def _format_context_pack_ultracompact(pack: dict) -> list[str]:
    path_ids: dict[str, str] = {}
    lines: list[str] = []
    common_header, per_file_imports = _get_import_compression_meta(pack)

    base = pack.get("base")
    head = pack.get("head")
    if base or head:
        lines.append(f"## Diff Context: {base}..{head}")
        lines.append("")

    # Show cache stats if present (delta mode)
    cache_stats = pack.get("cache_stats")
    if cache_stats:
        hit_rate = cache_stats.get("hit_rate", 0)
        hits = cache_stats.get("hits", 0)
        misses = cache_stats.get("misses", 0)
        lines.append(f"# Delta: {hits} unchanged, {misses} changed ({hit_rate:.0%} cache hit)")
        lines.append("")

    if common_header:
        lines.extend(common_header.splitlines())
        lines.append("")

    for item in pack.get("slices", []):
        _format_symbol(item.get("id", "?"), "", path_ids)

    if path_ids:
        header = " ".join([f"{pid}={path}" for path, pid in path_ids.items()])
        lines.append(header)
        lines.append("")

    # Handle both boolean (new format) and list (legacy format) for unchanged
    unchanged_val = pack.get("unchanged", [])
    if isinstance(unchanged_val, bool):
        unchanged_set = set()  # Boolean format doesn't list individual IDs
    else:
        unchanged_set = set(unchanged_val or [])

    seen_import_files: set[str] = set()
    for item in pack.get("slices", []):
        symbol_id = item.get("id", "?")
        file_part, _ = _split_symbol(symbol_id, "")
        if file_part and file_part not in seen_import_files:
            seen_import_files.add(file_part)
            unique_imports = per_file_imports.get(file_part, "").strip()
            if unique_imports:
                file_label = path_ids.get(file_part, file_part)
                lines.append(f"# Unique imports: {file_label}")
                for unique_line in unique_imports.splitlines():
                    lines.append(f"#   {unique_line}")

        display = _format_symbol(symbol_id, "", path_ids)
        signature = item.get("signature", "")
        lines_range = item.get("lines") or []
        line_info = ""
        if len(lines_range) == 2:
            line_info = f"@{lines_range[0]}-{lines_range[1]}"
        relevance = item.get("relevance", "")

        # Mark unchanged symbols
        unchanged_marker = " [UNCHANGED]" if symbol_id in unchanged_set else ""
        lines.append(f"{display} {signature} {line_info} [{relevance}]{unchanged_marker}".rstrip())

        code = item.get("code")
        if code:
            meta = item.get("meta")
            representation = meta.get("representation") if isinstance(meta, dict) else None
            if representation == "incremental":
                lines.extend(code.splitlines())
            else:
                lines.append("```")
                lines.extend(code.splitlines())
                lines.append("```")

        lines.append("")

    # Show rehydration info if present
    rehydrate = pack.get("rehydrate")
    if rehydrate:
        lines.append("# Rehydration refs (use to fetch full code):")
        for sym_id, vhs_ref in rehydrate.items():
            lines.append(f"#   {sym_id}: {vhs_ref}")
        lines.append("")

    return lines


def _take_prefix_by_bytes(lines: list[str], max_bytes: int) -> list[str]:
    kept: list[str] = []
    size = 0
    for line in lines:
        line_bytes = len((line + "\n").encode("utf-8"))
        if size + line_bytes > max_bytes:
            break
        kept.append(line)
        size += line_bytes
    return kept


def _trim_to_symbol_boundary(lines: list[str]) -> list[str]:
    """Rewind to the last complete symbol boundary.

    Primary boundary is a blank line (ultracompact and most text formats).
    Fallback boundary for text format is the start of the last `📍` block.
    """
    if not lines:
        return []
    if lines[-1].strip() == "":
        return lines

    trimmed = list(lines)
    while trimmed and trimmed[-1].strip():
        trimmed.pop()
    if trimmed:
        return trimmed

    symbol_starts = [idx for idx, line in enumerate(lines) if line.lstrip().startswith("📍")]
    if len(symbol_starts) >= 2:
        return lines[:symbol_starts[-1]]
    if len(symbol_starts) == 1 and symbol_starts[0] > 0:
        return lines[:symbol_starts[0]]
    return []


def truncate_output(text: str, max_lines: int | None = None, max_bytes: int | None = None) -> str:
    """Post-format text truncation. Returns text with TRUNCATED marker if capped."""
    if max_lines is None and max_bytes is None:
        return text

    original_lines = text.split("\n")
    lines = list(original_lines)
    truncated = False

    if max_lines and len(lines) > max_lines:
        lines = _trim_to_symbol_boundary(lines[:max_lines])
        truncated = True

    result = "\n".join(lines)
    if max_bytes and len(result.encode("utf-8")) > max_bytes:
        lines = _trim_to_symbol_boundary(_take_prefix_by_bytes(lines, max_bytes))
        result = "\n".join(lines)
        truncated = True

    result = result.rstrip("\n")
    omitted = max(0, len(original_lines) - len(lines))

    if truncated:
        parts = []
        if max_lines:
            parts.append(f"--max-lines={max_lines}")
        if max_bytes:
            parts.append(f"--max-bytes={max_bytes}")
        marker = f"[TRUNCATED: output exceeded {', '.join(parts)}"
        if omitted:
            marker += f"; omitted {omitted} lines"
        marker += "]"
        if result:
            result += f"\n\n{marker}"
        else:
            result = marker
    return result


def truncate_json_output(
    data: dict,
    max_lines: int | None = None,
    max_bytes: int | None = None,
    indent: int | None = None,
) -> str:
    """Truncate JSON output by dropping slices/lines from end until under caps."""
    import copy

    if max_lines is None and max_bytes is None:
        return json.dumps(data, indent=indent, ensure_ascii=False)
    d = copy.deepcopy(data)
    trim_key = "slices" if "slices" in d else ("lines" if "lines" in d else None)
    for _ in range(1000):
        out = json.dumps(d, indent=indent, ensure_ascii=False)
        over_lines = max_lines and out.count("\n") + 1 > max_lines
        over_bytes = max_bytes and len(out.encode("utf-8")) > max_bytes
        if not over_lines and not over_bytes:
            return out
        if trim_key and d.get(trim_key):
            d[trim_key] = d[trim_key][:-1]
            d["truncated"] = True
        else:
            break
    d["truncated"] = True
    return json.dumps(d, indent=indent, ensure_ascii=False)
