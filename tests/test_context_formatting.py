from tldr_swinton.engines.symbolkite import FunctionContext, RelevantContext


def test_context_indent_uses_depth() -> None:
    ctx = RelevantContext(
        entry_point="root",
        depth=2,
        functions=[
            FunctionContext(
                name="root",
                file="root.py",
                line=1,
                signature="def root():",
                depth=0,
            ),
            FunctionContext(
                name="child",
                file="child.py",
                line=5,
                signature="def child():",
                depth=2,
            ),
        ],
    )
    rendered = ctx.to_llm_string().splitlines()
    root_line = next(line for line in rendered if "root.py" in line)
    child_line = next(line for line in rendered if "child.py" in line)
    assert child_line.startswith("    ")
    assert not root_line.startswith("    ")
