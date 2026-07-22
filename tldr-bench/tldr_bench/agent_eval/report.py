from __future__ import annotations

import json
from pathlib import Path

from .analysis import EvaluationAnalysis


def _format_observed(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1%}"
    return str(value)


def render_markdown(analysis: EvaluationAnalysis) -> str:
    lines = [
        "# Paired tldrs Agent Value Evaluation",
        "",
        f"**Verdict:** {analysis.verdict.value.upper()}",
        "",
        "## Gates",
        "",
        "| Gate | Status | Observed | Threshold | Evidence |",
        "|---|---:|---:|---:|---|",
    ]
    for gate in analysis.gates:
        lines.append(
            f"| {gate.name} | {gate.status.value.upper()} | "
            f"{_format_observed(gate.observed)} | {gate.threshold} | {gate.detail} |"
        )

    lines.extend(
        [
            "",
            "## Pair Summary",
            "",
            f"- Paired cells: {analysis.metrics.pair_count}",
            f"- Baseline successes: {analysis.metrics.baseline_successes}",
            f"- Adaptive successes: {analysis.metrics.adaptive_successes}",
            f"- Routing recall: {_format_observed(analysis.metrics.routing_recall)}",
            "- Context owner recall: "
            f"{_format_observed(analysis.metrics.context_owner_recall)}",
        ]
    )
    if analysis.incomplete_cells:
        lines.extend(["", "## Incomplete Cells", ""])
        lines.extend(f"- {cell}" for cell in analysis.incomplete_cells)
    if analysis.contamination:
        lines.extend(["", "## Contamination", ""])
        lines.extend(f"- {item}" for item in analysis.contamination)

    lines.extend(["", "## Raw Paired Cells", ""])
    for pair in analysis.pairs:
        lines.append(
            f"- {pair.baseline.cell_id} ↔ {pair.adaptive.cell_id}: "
            f"success={pair.baseline.success}/{pair.adaptive.success}, "
            f"tokens={pair.baseline.trace.uncached_total_tokens}/"
            f"{pair.adaptive.trace.uncached_total_tokens}, "
            f"tldrs={pair.baseline.trace.tldrs_calls}/"
            f"{pair.adaptive.trace.tldrs_calls}"
        )
    return "\n".join(lines) + "\n"


def write_reports(
    analysis: EvaluationAnalysis, *, json_path: Path, markdown_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(analysis.to_dict(), indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_markdown(analysis))
