from tldr_swinton.api import FunctionContext, RelevantContext
from tldr_swinton.cli import _make_vhs_preview, _make_vhs_summary, _render_vhs_output


def test_make_vhs_preview_caps_lines_and_bytes() -> None:
    long_line = "x" * 3000
    text = "line1\n" + long_line + "\nline3\n"

    preview = _make_vhs_preview(text, max_lines=30, max_bytes=2048)

    assert preview.splitlines() == ["line1"]


def test_make_vhs_preview_caps_lines() -> None:
    lines = [f"line{i}" for i in range(40)]
    text = "\n".join(lines)

    preview = _make_vhs_preview(text, max_lines=30, max_bytes=99999)

    assert len(preview.splitlines()) == 30


def test_make_vhs_summary_counts() -> None:
    ctx = RelevantContext(
        entry_point="foo",
        depth=2,
        functions=[
            FunctionContext(
                name="a",
                file="one.py",
                line=1,
                signature="def a()",
            ),
            FunctionContext(
                name="b",
                file="two.py",
                line=2,
                signature="def b()",
            ),
        ],
    )

    summary = _make_vhs_summary(ctx)

    assert "Entry foo" in summary
    assert "depth=2" in summary
    assert "functions=2" in summary
    assert "files=2" in summary


def test_render_vhs_output_ref_first_line() -> None:
    output = _render_vhs_output("vhs://abc", "summary", "preview")
    lines = output.splitlines()
    assert lines[0] == "vhs://abc"
    assert any(line.startswith("# Summary:") for line in lines[1:])
