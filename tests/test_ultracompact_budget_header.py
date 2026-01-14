from tldr_swinton.api import FunctionContext, RelevantContext
from tldr_swinton.output_formats import _estimate_tokens, _format_ultracompact, format_context


def test_ultracompact_budget_falls_back_to_inline_when_header_too_large() -> None:
    calls = [f"deep/path/{i}/file{i}.py:callee{i}" for i in range(30)]
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
    header_line = lines[0]
    sig_line = lines[2]
    budget = _estimate_tokens([sig_line, ""]) + 1

    assert _estimate_tokens([header_line, ""]) > budget

    output = format_context(ctx, fmt="ultracompact", budget_tokens=budget)
    assert "P0=" not in output
    assert "P0:" not in output
    assert "src/main.py:foo" in output
