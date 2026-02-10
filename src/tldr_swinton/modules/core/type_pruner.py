"""Type-directed context pruning for caller/callee expansion."""
from __future__ import annotations

from dataclasses import dataclass, is_dataclass, replace
import re
from typing import Any

_SIDE_EFFECT_MARKERS = ("global ", "nonlocal ", "open(", "write(", "print(")

_STDLIB_MODULES = {
    "os",
    "sys",
    "json",
    "pathlib",
    "collections",
    "typing",
    "dataclasses",
    "functools",
    "itertools",
    "re",
    "hashlib",
    "datetime",
    "logging",
    "math",
    "string",
    "io",
    "copy",
    "shutil",
    "subprocess",
    "tempfile",
    "urllib",
    "http",
    "socket",
    "asyncio",
    "concurrent",
    "threading",
    "unittest",
    "pytest",
}

_FRAMEWORK_PREFIXES = (
    "flask.",
    "fastapi.",
    "django.",
    "sqlalchemy.",
    "pytest.",
    "click.",
    "typer.",
)


@dataclass(frozen=True)
class _CallerView:
    index: int
    symbol_id: str
    signature: str
    code: str | None
    candidate: Any


def _split_args(params: str) -> list[str]:
    if not params.strip():
        return []
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in params:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                parts.append(token)
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_name_from_signature(signature: str, symbol_id: str = "") -> str:
    text = signature.strip()
    for pattern in (
        r"(?:async\s+)?def\s+([A-Za-z_][\w]*)\s*\(",
        r"(?:async\s+)?function\s+([A-Za-z_][\w]*)\s*\(",
        r"(?:async\s+)?fn\s+([A-Za-z_][\w]*)\s*\(",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    if "(" in text:
        prefix = text.split("(", 1)[0].strip()
        if prefix:
            return prefix.split()[-1]
    qualified = symbol_id.split(":", 1)[-1] if symbol_id else ""
    if qualified:
        return qualified.split(".")[-1]
    return "unknown"


def _extract_param_count(signature: str) -> int:
    if "(" not in signature or ")" not in signature:
        return 0
    body = signature.split("(", 1)[1].split(")", 1)[0]
    params = [p.strip() for p in _split_args(body)]
    return sum(1 for p in params if p and p not in {"self", "cls", "/", "*"})


def _extract_pattern(signature: str, symbol_id: str = "") -> str:
    name = _extract_name_from_signature(signature, symbol_id=symbol_id)
    argc = _extract_param_count(signature)
    return f"{name}/{argc}"


def _has_typed_params(signature: str) -> bool:
    if "(" not in signature or ")" not in signature:
        return False
    body = signature.split("(", 1)[1].split(")", 1)[0]
    params = [p.strip() for p in _split_args(body)]
    typed = 0
    total = 0
    for param in params:
        if not param or param in {"self", "cls", "/", "*"}:
            continue
        total += 1
        left = param.split("=", 1)[0].strip()
        if ":" in left:
            typed += 1
    return total > 0 and typed == total


def is_self_documenting(signature: str, code: str | None, line_count: int = 0) -> bool:
    """Return True when signature/body likely self-document the contract."""
    sig = (signature or "").strip()
    if not sig or "->" not in sig:
        return False
    if not _has_typed_params(sig):
        return False

    if code is not None:
        body_lines = [line for line in code.splitlines() if line.strip()]
        if len(body_lines) >= 10:
            return False
        lowered = code.lower()
        if any(marker in lowered for marker in _SIDE_EFFECT_MARKERS):
            return False
    elif line_count >= 10:
        return False

    return True


def is_stdlib_or_framework(symbol_id: str) -> bool:
    """Return True for standard library, framework, and test helper symbols."""
    raw = (symbol_id or "").strip()
    lowered = raw.lower()
    qualified = lowered.split(":", 1)[-1]

    if ".test_" in lowered or lowered.startswith("test_") or qualified.startswith("test_"):
        return True

    for module in _STDLIB_MODULES:
        if qualified == module or qualified.startswith(f"{module}."):
            return True

    for prefix in _FRAMEWORK_PREFIXES:
        if qualified.startswith(prefix):
            return True

    return False


def group_callers_by_pattern(callers: list[dict]) -> list[dict]:
    """Group callers by function name + argument count pattern."""
    groups: dict[str, dict] = {}
    for idx, caller in enumerate(callers):
        signature = str(caller.get("signature", "") or "")
        symbol_id = str(caller.get("symbol_id", "") or "")
        pattern = _extract_pattern(signature, symbol_id=symbol_id)
        existing = groups.get(pattern)
        if existing is None:
            groups[pattern] = {"exemplar": caller, "count": 1, "pattern": pattern, "_first_idx": idx}
        else:
            existing["count"] += 1

    ordered = sorted(groups.values(), key=lambda g: (-int(g["count"]), int(g["_first_idx"])))
    for item in ordered:
        item.pop("_first_idx", None)
    return ordered


def _get_field(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _with_updates(candidate: Any, **updates: Any) -> Any:
    if isinstance(candidate, dict):
        out = dict(candidate)
        out.update(updates)
        return out
    if is_dataclass(candidate):
        return replace(candidate, **updates)
    for key, value in updates.items():
        setattr(candidate, key, value)
    return candidate


def _append_reason(candidate: Any, reason: str, extra: dict[str, Any] | None = None) -> Any:
    meta = _get_field(candidate, "meta")
    if not isinstance(meta, dict):
        meta = {}
    reasons = meta.get("pruned_reason")
    if isinstance(reasons, list):
        reason_list = list(reasons)
    elif isinstance(reasons, str) and reasons:
        reason_list = [reasons]
    else:
        reason_list = []
    if reason not in reason_list:
        reason_list.append(reason)
    meta["pruned_reason"] = reason_list
    if extra:
        meta.update(extra)
    return _with_updates(candidate, meta=meta)


def _is_caller(candidate: Any) -> bool:
    return _get_field(candidate, "relevance_label") == "caller"


def prune_expansion(
    candidates: list,
    callee_signature: str = "",
    callee_code: str | None = None,
    max_callers: int = 5,
) -> list:
    """Apply self-documenting/stdlib/pattern dedupe pruning to candidates."""
    if not candidates:
        return []
    max_callers = max(0, max_callers)

    pruned: list[Any] = []
    for candidate in candidates:
        symbol_id = str(_get_field(candidate, "symbol_id", "") or "")
        if is_stdlib_or_framework(symbol_id):
            continue
        pruned.append(candidate)

    if is_self_documenting(callee_signature, callee_code):
        updated: list[Any] = []
        for candidate in pruned:
            if _is_caller(candidate):
                if _get_field(candidate, "code") is not None:
                    candidate = _with_updates(candidate, code=None)
                candidate = _append_reason(candidate, "self_documenting_callee_signature_only")
            updated.append(candidate)
        pruned = updated

    callers: list[_CallerView] = []
    for idx, candidate in enumerate(pruned):
        if _is_caller(candidate):
            callers.append(
                _CallerView(
                    index=idx,
                    symbol_id=str(_get_field(candidate, "symbol_id", "") or ""),
                    signature=str(_get_field(candidate, "signature", "") or ""),
                    code=_get_field(candidate, "code"),
                    candidate=candidate,
                )
            )

    if len(callers) <= max_callers:
        return pruned

    grouped = group_callers_by_pattern(
        [
            {
                "symbol_id": item.symbol_id,
                "signature": item.signature,
                "code": item.code,
                "_view": item,
            }
            for item in callers
        ]
    )

    keep_views = [group["exemplar"]["_view"] for group in grouped[:max_callers]]
    keep_indexes = {view.index for view in keep_views}

    updates_by_index: dict[int, Any] = {}
    for group in grouped[:max_callers]:
        view = group["exemplar"]["_view"]
        updates_by_index[view.index] = _append_reason(
            view.candidate,
            "caller_pattern_dedup",
            {
                "caller_group_count": group["count"],
                "caller_group_pattern": group["pattern"],
            },
        )

    final: list[Any] = []
    for idx, candidate in enumerate(pruned):
        if _is_caller(candidate) and idx not in keep_indexes:
            continue
        final.append(updates_by_index.get(idx, candidate))
    return final


__all__ = [
    "group_callers_by_pattern",
    "is_self_documenting",
    "is_stdlib_or_framework",
    "prune_expansion",
]
