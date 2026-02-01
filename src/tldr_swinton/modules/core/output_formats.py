"""Context output formatting helpers."""

from __future__ import annotations

import json
from typing import Iterable

# Cached tiktoken encoder to avoid repeated initialization
_TIKTOKEN_ENCODER = None

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
                    "code": None,  # RelevantContext doesn't have code bodies
                    "lines": [func.line, func.line] if func.line else None,
                    "relevance": f"depth_{func.depth}",
                }
                for func in ctx.functions
            ],
            "unchanged": [],  # No delta info in RelevantContext
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
    result = {
        "budget_used": pack.budget_used,
        "slices": [
            {
                "id": item.id,
                "signature": item.signature,
                "code": item.code,
                "lines": list(item.lines) if item.lines else None,
                "relevance": item.relevance,
                "meta": item.meta,
                "etag": item.etag,
            }
            for item in pack.slices
        ],
    }
    # Include delta-specific fields if present
    if pack.unchanged:
        result["unchanged"] = pack.unchanged
    if pack.rehydrate:
        result["rehydrate"] = pack.rehydrate
    if pack.cache_stats:
        result["cache_stats"] = pack.cache_stats
    return result


def format_context_pack(pack: dict | ContextPack, fmt: str = "ultracompact") -> str:
    """Format a DiffLens-style ContextPack."""
    # Handle legacy string "UNCHANGED" (for backwards compatibility)
    if pack == "UNCHANGED":
        pack = {"unchanged": True, "budget_used": 0, "slices": []}

    if isinstance(pack, ContextPack):
        pack = _contextpack_to_dict(pack)

    # Handle structured unchanged response
    if isinstance(pack, dict) and pack.get("unchanged") is True and not pack.get("slices"):
        if fmt in ("json", "json-pretty"):
            return json.dumps(pack, indent=2 if fmt == "json-pretty" else None, ensure_ascii=False)
        return "# UNCHANGED (no changes since last request)"
    # Handle error responses (including ambiguous)
    if isinstance(pack, dict) and pack.get("error") is True:
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


def _estimate_tokens(text_or_lines: str | Iterable[str]) -> int:
    if isinstance(text_or_lines, str):
        text = text_or_lines
    else:
        text = "\n".join(text_or_lines)

    encoder = _get_tiktoken_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)


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
        line_info = f"@{func.line}" if func.line else ""
        lines.append(f"{display} {signature} {line_info}".rstrip())

        if func.calls:
            calls_list = _dedupe_preserve(func.calls)
            shown = calls_list[:max_calls]
            more = len(calls_list) - len(shown)
            calls = ", ".join(_format_symbol(c, "", path_ids) for c in shown)
            suffix = f" (+{more})" if more > 0 else ""
            lines.append(f"  calls: {calls}{suffix}")

        lines.append("")

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
        line_info = f"@{func.line}" if func.line else ""
        func_lines.append(f"{display} {signature} {line_info}".rstrip())
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
        func_lines.append("")
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


def _format_cache_friendly(pack: dict) -> str:
    """Format context pack for LLM provider prompt caching optimization.

    Separates output into:
    1. CACHE PREFIX (stable): Unchanged symbols with signatures only, sorted by ID
    2. CACHE_BREAKPOINT marker with token estimate
    3. DYNAMIC CONTENT (changes): Changed symbols with full code, sorted by relevance

    This format is optimized for:
    - Anthropic prompt caching (90% cost savings on cached prefix)
    - OpenAI prompt caching (50% cost savings on cached prefix)

    Args:
        pack: ContextPack dict with slices, unchanged list, etc.

    Returns:
        Formatted string with cache-friendly structure
    """
    lines: list[str] = []
    lines.append("# tldrs cache-friendly output")
    lines.append("")

    slices = pack.get("slices", [])
    if not slices:
        lines.append("# No symbols to display")
        return "\n".join(lines)

    # Separate unchanged (cache prefix) from changed (dynamic)
    # Handle both boolean (new format) and list (legacy format) for unchanged
    unchanged_val = pack.get("unchanged", [])
    if isinstance(unchanged_val, bool):
        unchanged_set = set()  # Boolean format doesn't list individual IDs
    else:
        unchanged_set = set(unchanged_val or [])

    prefix_slices: list[dict] = []
    dynamic_slices: list[dict] = []

    for item in slices:
        symbol_id = item.get("id", "?")
        if symbol_id in unchanged_set:
            prefix_slices.append(item)
        else:
            dynamic_slices.append(item)

    # Sort prefix by symbol ID for stable ordering (cache-friendly)
    prefix_slices.sort(key=lambda s: s.get("id", ""))

    # Sort dynamic by relevance (most relevant first)
    relevance_order = {"contains_diff": 0, "caller": 1, "callee": 2, "adjacent": 3}
    dynamic_slices.sort(key=lambda s: (relevance_order.get(s.get("relevance", ""), 99), s.get("id", "")))

    # Estimate tokens for each section
    def _est_tokens(text: str) -> int:
        encoder = _get_tiktoken_encoder()
        if encoder is not None:
            return len(encoder.encode(text))
        return max(1, len(text) // 4)

    # Build cache prefix section
    prefix_lines: list[str] = []
    prefix_token_est = 0

    if prefix_slices:
        prefix_lines.append(f"## CACHE PREFIX (stable - cache this section)")
        prefix_lines.append(f"## {len(prefix_slices)} symbols")
        prefix_lines.append("")

        for item in prefix_slices:
            symbol_id = item.get("id", "?")
            signature = item.get("signature", "")
            lines_range = item.get("lines") or []
            line_info = ""
            if lines_range and len(lines_range) == 2:
                line_info = f" @{lines_range[0]}"
            relevance = item.get("relevance", "")

            # Format: file:symbol signature @line [relevance]
            entry = f"{symbol_id} {signature}{line_info} [{relevance}]".strip()
            prefix_lines.append(entry)

        prefix_lines.append("")
        prefix_text = "\n".join(prefix_lines)
        prefix_token_est = _est_tokens(prefix_text)

    # Build dynamic section
    dynamic_lines: list[str] = []
    dynamic_token_est = 0

    if dynamic_slices:
        # Count symbols with code for summary
        symbols_with_code = sum(1 for s in dynamic_slices if s.get("code"))
        dynamic_lines.append(f"## DYNAMIC CONTENT (changes per request)")
        dynamic_lines.append(f"## {len(dynamic_slices)} symbols, {symbols_with_code} with code")
        dynamic_lines.append("")

        for item in dynamic_slices:
            symbol_id = item.get("id", "?")
            signature = item.get("signature", "")
            lines_range = item.get("lines") or []
            line_info = ""
            if lines_range and len(lines_range) == 2:
                line_info = f" @{lines_range[0]}-{lines_range[1]}"
            relevance = item.get("relevance", "")

            entry = f"{symbol_id} {signature}{line_info} [{relevance}]".strip()
            dynamic_lines.append(entry)

            code = item.get("code")
            if code:
                dynamic_lines.append("```")
                dynamic_lines.extend(code.splitlines())
                dynamic_lines.append("```")

            dynamic_lines.append("")

        dynamic_text = "\n".join(dynamic_lines)
        dynamic_token_est = _est_tokens(dynamic_text)

    # Assemble output
    if prefix_slices:
        lines.extend(prefix_lines)
        lines.append(f"<!-- CACHE_BREAKPOINT: ~{prefix_token_est} tokens -->")
        lines.append("")

    if dynamic_slices:
        lines.extend(dynamic_lines)

    # Stats footer
    total_tokens = prefix_token_est + dynamic_token_est
    lines.append(f"## STATS: Prefix ~{prefix_token_est} tokens | Dynamic ~{dynamic_token_est} tokens | Total ~{total_tokens} tokens")

    # Cache stats if available
    cache_stats = pack.get("cache_stats")
    if cache_stats:
        hit_rate = cache_stats.get("hit_rate", 0)
        hits = cache_stats.get("hits", 0)
        misses = cache_stats.get("misses", 0)
        lines.append(f"## Cache: {hits} unchanged, {misses} changed ({hit_rate:.0%} hit rate)")

    return "\n".join(lines)


def _format_context_pack_ultracompact(pack: dict) -> list[str]:
    path_ids: dict[str, str] = {}
    lines: list[str] = []

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

    for item in pack.get("slices", []):
        symbol_id = item.get("id", "?")
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


def truncate_output(text: str, max_lines: int | None = None, max_bytes: int | None = None) -> str:
    """Post-format text truncation. Returns text with TRUNCATED marker if capped."""
    if max_lines is None and max_bytes is None:
        return text
    lines = text.split("\n")
    truncated = False
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    result = "\n".join(lines)
    if max_bytes and len(result.encode("utf-8")) > max_bytes:
        result = result.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        truncated = True
    if truncated:
        parts = []
        if max_lines:
            parts.append(f"--max-lines={max_lines}")
        if max_bytes:
            parts.append(f"--max-bytes={max_bytes}")
        result += f"\n[TRUNCATED: output exceeded {', '.join(parts)}]"
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
