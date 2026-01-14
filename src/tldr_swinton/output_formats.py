"""Context output formatting helpers."""

from __future__ import annotations

import json
from typing import Iterable

from .api import RelevantContext


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
            return "\n".join(_format_ultracompact(ctx))
        raise ValueError(f"Unknown format: {fmt}")

    if fmt == "text":
        return _format_text_budgeted(ctx, budget_tokens)
    if fmt == "ultracompact":
        return _format_ultracompact_budgeted(ctx, budget_tokens)
    raise ValueError(f"Unknown format: {fmt}")


def format_context_pack(pack: dict, fmt: str = "ultracompact") -> str:
    """Format a DiffLens-style ContextPack."""
    if fmt == "json":
        return json.dumps(pack, indent=2)
    if fmt == "ultracompact":
        return "\n".join(_format_context_pack_ultracompact(pack))
    raise ValueError(f"Unknown format: {fmt}")


def _apply_budget(lines: Iterable[str], budget_tokens: int) -> list[str]:
    used = 0
    output: list[str] = []
    for line in lines:
        est = max(1, len(line) // 4)
        if used + est > budget_tokens:
            output.append("... (budget reached)")
            break
        output.append(line)
        used += est
    return output


def _estimate_tokens(lines: Iterable[str]) -> int:
    return sum(max(1, len(line) // 4) for line in lines)


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


def _format_ultracompact(ctx: RelevantContext) -> list[str]:
    path_ids: dict[str, str] = {}
    lines: list[str] = []

    for func in ctx.functions:
        _format_symbol(func.name, func.file, path_ids)

        for callee in func.calls:
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
            calls = ", ".join(_format_symbol(c, "", path_ids) for c in func.calls)
            lines.append(f"  calls: {calls}")

        lines.append("")

    return lines


def _format_ultracompact_budgeted(ctx: RelevantContext, budget_tokens: int) -> str:
    path_ids: dict[str, str] = {}
    lines: list[str] = []
    used = 0

    funcs = sorted(
        enumerate(ctx.functions),
        key=lambda pair: (pair[1].depth, pair[0]),
    )

    def render_func(func, include_calls: bool) -> list[str]:
        func_lines: list[str] = []
        display = _format_symbol(func.name, func.file, path_ids)
        signature = func.signature
        line_info = f"@{func.line}" if func.line else ""
        func_lines.append(f"{display} {signature} {line_info}".rstrip())
        if include_calls and func.calls:
            calls = ", ".join(_format_symbol(c, "", path_ids) for c in func.calls)
            func_lines.append(f"  calls: {calls}")
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
        elif collected_cost > budget_tokens:
            lines.extend(_apply_budget(collected, budget_tokens))
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

    for item in pack.get("slices", []):
        _format_symbol(item.get("id", "?"), "", path_ids)

    if path_ids:
        header = " ".join([f"{pid}={path}" for path, pid in path_ids.items()])
        lines.append(header)
        lines.append("")

    for item in pack.get("slices", []):
        symbol_id = item.get("id", "?")
        display = _format_symbol(symbol_id, "", path_ids)
        signature = item.get("signature", "")
        lines_range = item.get("lines") or []
        line_info = ""
        if len(lines_range) == 2:
            line_info = f"@{lines_range[0]}-{lines_range[1]}"
        relevance = item.get("relevance", "")
        lines.append(f"{display} {signature} {line_info} [{relevance}]".rstrip())

        code = item.get("code")
        if code:
            lines.append("  code:")
            for code_line in code.splitlines():
                lines.append(f"  {code_line}")

        lines.append("")

    sig_only = pack.get("signatures_only") or []
    if sig_only:
        sigs = ", ".join(_format_symbol(s, "", path_ids) for s in sig_only)
        lines.append(f"signatures_only: {sigs}")

    return lines
