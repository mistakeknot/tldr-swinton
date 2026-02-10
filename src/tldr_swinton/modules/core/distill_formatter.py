"""Distillation formatter — compress multi-source analysis into prescriptive summaries."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DistilledContext:
    files_to_edit: list[dict] = field(default_factory=list)
    # Each: {"path": str, "symbol": str, "lines": (int,int), "reason": str}
    key_functions: list[dict] = field(default_factory=list)
    # Each: {"signature": str, "returns": str, "calls": list[str]}
    dependencies: list[dict] = field(default_factory=list)
    # Each: {"caller": str, "path": str, "line": int, "relationship": str}
    risk_areas: list[dict] = field(default_factory=list)
    # Each: {"location": str, "risk": str}
    summary: str = ""
    token_estimate: int = 0


def _estimate_tokens(text: str) -> int:
    return max(0, len(text) // 4)


def _split_symbol_id(symbol_id: str) -> tuple[str, str]:
    if ":" not in symbol_id:
        return "?", symbol_id or "?"
    path, symbol = symbol_id.split(":", 1)
    return path or "?", symbol or "?"


def _coerce_lines(value: object) -> tuple[int, int]:
    if isinstance(value, tuple) and len(value) == 2:
        return int(value[0]), int(value[1])
    if isinstance(value, list) and len(value) >= 2:
        return int(value[0]), int(value[1])
    return 0, 0


def _extract_returns(signature: str) -> str:
    if "->" in signature:
        return signature.rsplit("->", 1)[-1].strip()
    if ":" in signature and ")" in signature:
        trailer = signature.rsplit(":", 1)[-1].strip()
        if trailer:
            return trailer
    return "unknown"


def _extract_calls(meta: object) -> list[str]:
    if not isinstance(meta, dict):
        return []
    raw = meta.get("calls") or meta.get("callees")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return []


def _extract_callers(meta: object) -> list[dict]:
    if not isinstance(meta, dict):
        return []
    raw = meta.get("callers")
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _extract_risks(meta: object) -> list[str]:
    if not isinstance(meta, dict):
        return []
    raw = meta.get("risks") or meta.get("risk")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return []


def _render_lines(lines: tuple[int, int]) -> str:
    start, end = lines
    if start <= 0:
        return "lines ?-?"
    if end <= 0:
        return f"line {start}"
    return f"lines {start}-{end}"


def format_distilled(context: DistilledContext, budget: int = 1500) -> str:
    files_to_edit = list(context.files_to_edit)
    key_functions = list(context.key_functions)
    dependencies = list(context.dependencies)
    risk_areas = list(context.risk_areas)
    summary = (context.summary or "").strip() or "No distilled summary available."

    def render() -> str:
        lines: list[str] = ["## Files to Edit"]
        if files_to_edit:
            for item in files_to_edit:
                path = str(item.get("path", "?"))
                symbol = str(item.get("symbol", "?"))
                reason = str(item.get("reason", "")).strip()
                span = _render_lines(_coerce_lines(item.get("lines")))
                entry = f"- {path}: {symbol} ({span})"
                if reason:
                    entry += f" — {reason}"
                lines.append(entry)
        else:
            lines.append("- No concrete edit targets identified")

        lines.append("")
        lines.append("## Key Functions")
        if key_functions:
            for item in key_functions:
                signature = str(item.get("signature", "?"))
                returns = str(item.get("returns", "unknown"))
                calls = item.get("calls")
                if not isinstance(calls, list):
                    calls = []
                calls_text = ", ".join(str(call) for call in calls) if calls else "none"
                lines.append(f"- {signature} → {returns}, calls: {calls_text}")
        else:
            lines.append("- None")

        lines.append("")
        lines.append("## Dependencies (will break if changed)")
        if dependencies:
            for item in dependencies:
                caller = str(item.get("caller", "?"))
                path = str(item.get("path", "?"))
                line = int(item.get("line", 0) or 0)
                relationship = str(item.get("relationship", "calls target directly"))
                lines.append(f"- {caller} ({path}:{line}) {relationship}")
        else:
            lines.append("- None")

        lines.append("")
        lines.append("## Risk Areas")
        if risk_areas:
            for item in risk_areas:
                location = str(item.get("location", "?"))
                risk = str(item.get("risk", "Unknown risk"))
                lines.append(f"- {location}: {risk}")
        else:
            lines.append("- None")

        lines.append("")
        lines.append("## Summary")
        lines.append(summary)
        return "\n".join(lines)

    rendered = render()
    while _estimate_tokens(rendered) > budget and risk_areas:
        risk_areas.pop()
        rendered = render()
    while _estimate_tokens(rendered) > budget and dependencies:
        dependencies.pop()
        rendered = render()
    while _estimate_tokens(rendered) > budget and key_functions:
        key_functions.pop()
        rendered = render()
    while _estimate_tokens(rendered) > budget and len(summary) > 80:
        summary = summary[:-80].rstrip() + "..."
        rendered = render()
    return rendered


def distill_from_candidates(candidates: list, task: str, budget: int = 1500) -> DistilledContext:
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: int(getattr(candidate, "relevance", 0) or 0),
        reverse=True,
    )

    distilled = DistilledContext()
    seen_keys: set[str] = set()
    seen_deps: set[tuple[str, str, int, str]] = set()
    seen_risks: set[tuple[str, str]] = set()

    for candidate in sorted_candidates:
        symbol_id = str(getattr(candidate, "symbol_id", ""))
        path, symbol = _split_symbol_id(symbol_id)
        lines = _coerce_lines(getattr(candidate, "lines", None))
        relevance = int(getattr(candidate, "relevance", 0) or 0)
        signature = str(getattr(candidate, "signature", "") or f"def {symbol}(...)")
        meta = getattr(candidate, "meta", None)
        calls = _extract_calls(meta)

        if getattr(candidate, "code", None):
            distilled.files_to_edit.append(
                {
                    "path": path,
                    "symbol": symbol,
                    "lines": lines,
                    "reason": f"high relevance ({relevance})",
                }
            )

        key_id = f"{path}:{symbol}:{signature}"
        if key_id not in seen_keys:
            seen_keys.add(key_id)
            distilled.key_functions.append(
                {
                    "signature": signature,
                    "returns": _extract_returns(signature),
                    "calls": calls,
                }
            )

        for caller_info in _extract_callers(meta):
            caller = str(caller_info.get("caller", "unknown"))
            caller_path = str(caller_info.get("path", path))
            caller_line = int(caller_info.get("line", 0) or 0)
            relationship = str(caller_info.get("relationship", "calls target directly"))
            dep_key = (caller, caller_path, caller_line, relationship)
            if dep_key not in seen_deps:
                seen_deps.add(dep_key)
                distilled.dependencies.append(
                    {
                        "caller": caller,
                        "path": caller_path,
                        "line": caller_line,
                        "relationship": relationship,
                    }
                )

        if str(getattr(candidate, "relevance_label", "")) == "caller":
            dep_key = (symbol, path, lines[0], "calls target directly")
            if dep_key not in seen_deps:
                seen_deps.add(dep_key)
                distilled.dependencies.append(
                    {
                        "caller": symbol,
                        "path": path,
                        "line": lines[0],
                        "relationship": "calls target directly",
                    }
                )

        for risk in _extract_risks(meta):
            risk_key = (f"{path}:{symbol}", risk)
            if risk_key not in seen_risks:
                seen_risks.add(risk_key)
                distilled.risk_areas.append({"location": f"{path}:{symbol}", "risk": risk})

    if not distilled.files_to_edit and sorted_candidates:
        top = sorted_candidates[0]
        path, symbol = _split_symbol_id(str(getattr(top, "symbol_id", "")))
        distilled.files_to_edit.append(
            {
                "path": path,
                "symbol": symbol,
                "lines": _coerce_lines(getattr(top, "lines", None)),
                "reason": "top candidate by relevance",
            }
        )

    top_files = [item.get("path", "?") for item in distilled.files_to_edit[:3]]
    if top_files:
        file_text = ", ".join(str(item) for item in top_files)
        distilled.summary = (
            f"Task: {task}. Start in {file_text}, then validate dependencies and side effects before editing."
        )
    else:
        distilled.summary = f"Task: {task}. No concrete symbols were resolved; locate likely entry points first."

    distilled.token_estimate = _estimate_tokens(format_distilled(distilled, budget=budget))
    return distilled
