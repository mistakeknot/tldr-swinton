from tldr_swinton.api import FunctionContext, RelevantContext
from tldr_swinton.output_formats import _format_ultracompact, format_context


def test_ultracompact_caps_and_dedupes_calls() -> None:
    """Test that call lists are capped and deduped based on budget."""
    # Create 25 calls - more than MAX_CALLS_MAX (20)
    calls = [f"mod.py:callee{i}" for i in range(25)]
    ctx = RelevantContext(
        entry_point="foo",
        depth=0,
        functions=[
            FunctionContext(
                name="foo",
                file="src/main.py",
                line=1,
                signature="def foo():",
                docstring=None,
                calls=calls,
                depth=0,
            )
        ],
    )

    # With no budget, should use default MAX_CALLS (12)
    lines = _format_ultracompact(ctx, budget_tokens=None)
    calls_line = next(line for line in lines if line.strip().startswith("calls:"))
    assert "(+13)" in calls_line  # 25 - 12 = 13 hidden

    # With high budget, uses MAX_CALLS_MAX (20)
    output = format_context(ctx, fmt="ultracompact", budget_tokens=10000)
    assert "(+5)" in output  # 25 - 20 = 5 hidden

    # With low budget, uses fewer calls
    output_low = format_context(ctx, fmt="ultracompact", budget_tokens=1500)
    assert "(+20)" in output_low  # 25 - 5 = 20 hidden (budget < 2000 = 5 calls)
