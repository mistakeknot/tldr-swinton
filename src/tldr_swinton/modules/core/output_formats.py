"""Context output formatting helpers."""

from __future__ import annotations

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


def format_context(
    ctx: RelevantContext,
    fmt: str = "text",
    budget_tokens: int | None = None,
) -> str:
    """Format RelevantContext for output.

    Args:
        ctx: RelevantContext instance
        fmt: "text" or "ultracompact"
        budget_tokens: Optional token budget (approximate, len/4)
    """
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
    if isinstance(pack, dict) and pack.get("ambiguous"):
        # Use structured error format
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


def _estimate_tokens(text_or_lines: str | Iterable[str]) -> int:
    if isinstance(text_or_lines, str):
        text = text_or_lines
    else:
        text = "\n".join(text_or_lines)

    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
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
