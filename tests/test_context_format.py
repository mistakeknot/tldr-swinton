from tldr_swinton.api import FunctionContext, RelevantContext
from tldr_swinton.output_formats import format_context


def test_format_context_budget_degrades_detail() -> None:
    ctx = RelevantContext(
        entry_point="entry",
        depth=1,
        functions=[
            FunctionContext(
                name="a.py:alpha",
                file="a.py",
                line=1,
                signature="def alpha(x):",
                docstring="First function doc",
                calls=["b.py:beta"],
                depth=0,
                blocks=2,
                cyclomatic=2,
            ),
            FunctionContext(
                name="b.py:beta",
                file="b.py",
                line=10,
                signature="def beta(y):",
                docstring="Second function doc",
                calls=[],
                depth=1,
            ),
        ],
    )

    output = format_context(ctx, fmt="text", budget_tokens=40)
    assert "def alpha" in output
    assert "→ calls" in output or "budget reached" in output
