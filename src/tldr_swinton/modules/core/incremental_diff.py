"""Incremental diff delivery for partially changed symbols."""
from __future__ import annotations

import difflib


def compute_symbol_diff(old_code: str, new_code: str, context_lines: int = 3) -> str | None:
    """Return unified diff for a symbol body, or None if unchanged."""
    if old_code == new_code:
        return None

    diff = "".join(
        difflib.unified_diff(
            old_code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            n=context_lines,
        )
    )
    return diff or None


def is_diff_worthwhile(diff: str, full_code: str, threshold: float = 0.7) -> bool:
    """Check if sending a diff is smaller and simple enough than full code."""
    hunk_count = sum(1 for line in diff.splitlines() if line.startswith("@@"))
    if hunk_count > 5:
        return False
    return len(diff) < len(full_code) * threshold


def format_incremental(symbol_id: str, signature: str, diff: str, base_etag: str) -> str:
    """Format incremental payload for LLM-friendly delivery."""
    etag_prefix = base_etag[:8]
    diff_body = diff if diff.endswith("\n") else f"{diff}\n"
    return (
        f"## {symbol_id} [INCREMENTAL from etag:{etag_prefix}]\n"
        f"{signature}\n"
        f"{diff_body}"
    )
