from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tldr_bench.metrics import calculate_context_metrics, count_tokens  # noqa: E402


def test_calculate_context_metrics_json_pack() -> None:
    pack = {
        "slices": [
            {"id": "a.py:foo", "code": "line1\nline2", "lines": [1, 4]}
        ]
    }
    output = json.dumps(pack)
    baseline = "x" * 50
    budget = 25

    metrics = calculate_context_metrics(output, budget=budget, baseline=baseline)

    assert metrics.context_bytes == len(output.encode("utf-8"))
    assert metrics.context_tokens == count_tokens(output)
    assert metrics.symbols_included == 1
    assert metrics.symbols_signature_only == 0
    assert metrics.avg_code_tokens_per_symbol == count_tokens("line1\nline2")
    assert metrics.pct_symbol_body_included == 0.5
    assert metrics.windows_per_symbol == 1.0

    expected_compression = count_tokens(baseline) / max(1, metrics.context_tokens)
    assert metrics.compression_ratio == expected_compression

    expected_budget = 1.0 - abs(metrics.context_tokens - budget) / budget
    expected_budget = max(0.0, min(1.0, expected_budget))
    assert metrics.budget_compliance == expected_budget
