from tldr_swinton.modules.core.contextpack_engine import Candidate
from tldr_swinton.modules.core.distill_formatter import (
    DistilledContext,
    distill_from_candidates,
    format_distilled,
)


def test_distill_from_candidates_basic() -> None:
    candidates = [
        Candidate(
            symbol_id="src/worker.py:process",
            relevance=5,
            relevance_label="contains_diff",
            order=0,
            signature="def process(data) -> bool",
            code="def process(data):\n    return validate(data)\n",
            lines=(20, 45),
            meta={
                "calls": ["src/worker.py:validate"],
                "callers": [
                    {
                        "caller": "handle_request",
                        "path": "src/api.py",
                        "line": 12,
                        "relationship": "calls target directly",
                    }
                ],
                "risk": "shared mutable state",
            },
        ),
        Candidate(
            symbol_id="src/worker.py:validate",
            relevance=3,
            relevance_label="callee",
            order=1,
            signature="def validate(data) -> bool",
            code=None,
            lines=(48, 62),
            meta={"calls": []},
        ),
    ]

    distilled = distill_from_candidates(candidates, task="Fix process flow", budget=1500)

    assert isinstance(distilled, DistilledContext)
    assert distilled.files_to_edit
    assert any(item["signature"].startswith("def process") for item in distilled.key_functions)
    assert any(dep["caller"] == "handle_request" for dep in distilled.dependencies)
    assert distilled.summary.startswith("Task: Fix process flow")
    assert distilled.token_estimate > 0


def test_format_distilled_structure() -> None:
    context = DistilledContext(
        files_to_edit=[
            {"path": "src/a.py", "symbol": "run", "lines": (10, 20), "reason": "high relevance (5)"}
        ],
        key_functions=[
            {"signature": "def run() -> int", "returns": "int", "calls": ["dep()"]}
        ],
        dependencies=[
            {"caller": "main", "path": "src/main.py", "line": 8, "relationship": "calls target directly"}
        ],
        risk_areas=[{"location": "src/a.py:run", "risk": "concurrency risk"}],
        summary="Task summary.",
    )

    output = format_distilled(context, budget=1500)

    assert "## Files to Edit" in output
    assert "## Key Functions" in output
    assert "## Dependencies (will break if changed)" in output
    assert "## Risk Areas" in output
    assert "## Summary" in output


def test_format_distilled_budget_enforcement() -> None:
    context = DistilledContext(
        files_to_edit=[
            {"path": "src/a.py", "symbol": "run", "lines": (10, 20), "reason": "high relevance (5)"}
        ],
        key_functions=[
            {"signature": "def run() -> int", "returns": "int", "calls": ["dep()"]}
        ],
        dependencies=[
            {"caller": "main", "path": "src/main.py", "line": 8, "relationship": "calls target directly"}
        ],
        risk_areas=[
            {
                "location": "src/a.py:run",
                "risk": "very long risk detail " * 40,
            }
        ],
        summary="Short summary.",
    )

    output = format_distilled(context, budget=130)

    assert "main (src/main.py:8) calls target directly" in output
    assert "very long risk detail" not in output


def test_format_distilled_empty() -> None:
    distilled = distill_from_candidates([], task="Investigate parser", budget=1500)
    output = format_distilled(distilled, budget=1500)

    assert "## Files to Edit" in output
    assert "## Summary" in output
    assert "Task: Investigate parser" in output


def test_distilled_context_dataclass() -> None:
    context = DistilledContext()

    assert isinstance(context.files_to_edit, list)
    assert isinstance(context.key_functions, list)
    assert isinstance(context.dependencies, list)
    assert isinstance(context.risk_areas, list)
    assert isinstance(context.summary, str)
    assert isinstance(context.token_estimate, int)


def test_format_distilled_files_always_present() -> None:
    context = DistilledContext(
        files_to_edit=[
            {"path": "src/core.py", "symbol": "run", "lines": (1, 2), "reason": "top candidate"}
        ],
        key_functions=[
            {"signature": "def run() -> int", "returns": "int", "calls": ["helper()"]}
        ],
        dependencies=[
            {"caller": "entry", "path": "src/main.py", "line": 1, "relationship": "calls target directly"}
        ],
        risk_areas=[{"location": "src/core.py:run", "risk": "test risk"}],
        summary="Short summary.",
    )

    output = format_distilled(context, budget=20)

    assert "## Files to Edit" in output
    assert "src/core.py: run" in output
