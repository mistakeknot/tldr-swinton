from __future__ import annotations

import json
from pathlib import Path
from statistics import median


def summarize_jsonl(path: Path) -> dict[str, float]:
    totals: list[float] = []
    context_ms: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("total_tokens") is not None:
            totals.append(row["total_tokens"])
        if row.get("context_ms") is not None:
            context_ms.append(row["context_ms"])
    return {
        "total_tokens_median": median(totals) if totals else 0,
        "context_ms_median": median(context_ms) if context_ms else 0,
    }
