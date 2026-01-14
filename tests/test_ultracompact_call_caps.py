from tldr_swinton.api import FunctionContext, RelevantContext
from tldr_swinton.output_formats import _format_ultracompact, format_context


def test_ultracompact_caps_and_dedupes_calls() -> None:
    calls = [f"mod.py:callee{i}" for i in range(14)]
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

    lines = _format_ultracompact(ctx)
    calls_line = next(line for line in lines if line.strip().startswith("calls:"))
    assert "(+2)" in calls_line

    output = format_context(ctx, fmt="ultracompact", budget_tokens=10000)
    assert "(+2)" in output
