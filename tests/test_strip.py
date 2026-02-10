import importlib.util

import pytest

from tldr_swinton.modules.core.strip import estimate_savings, strip_code


def test_strip_python_inline_comments() -> None:
    source = "x = 1  # comment\n"
    out = strip_code(source, "python")
    assert out.splitlines()[0].rstrip() == "x = 1"
    assert out.count("\n") == source.count("\n")


def test_preserve_todo_marker() -> None:
    source = "# TODO: fix this\nx = 1\n"
    out = strip_code(source, "python")
    assert "# TODO: fix this" in out


def test_preserve_fixme_marker() -> None:
    source = "# FIXME: broken\nx = 1\n"
    out = strip_code(source, "python")
    assert "# FIXME: broken" in out


def test_truncate_docstring() -> None:
    source = (
        "def f():\n"
        "    \"\"\"First line\n"
        "    second line\n"
        "    third line\"\"\"\n"
        "    return 1\n"
    )
    out = strip_code(source, "python")
    lines = out.splitlines()
    assert "\"\"\"First line" in lines[1]
    assert lines[2] == ""
    assert lines[3] == ""
    assert out.count("\n") == source.count("\n")


def test_line_count_preserved() -> None:
    source = (
        "x = 1  # remove\n"
        "def f():\n"
        "    \"\"\"Doc first\n"
        "    doc second\"\"\"\n"
        "    return x\n"
    )
    out = strip_code(source, "python")
    assert out.count("\n") == source.count("\n")


def test_strip_block_comment_js() -> None:
    if importlib.util.find_spec("tree_sitter_javascript") is None:
        pytest.skip("tree_sitter_javascript not installed")
    source = "const x = 1; /* remove\nmultiline */\nconst y = 2;\n"
    out = strip_code(source, "javascript")
    assert "remove" not in out
    assert "multiline" not in out
    assert out.count("\n") == source.count("\n")


def test_unsupported_language_passthrough() -> None:
    source = "x = 1 # keep\n"
    out = strip_code(source, "unknown-language")
    assert out == source


def test_empty_source() -> None:
    assert strip_code("", "python") == ""


def test_estimate_savings() -> None:
    source = "x = 1  # remove\n# TODO: keep\n"
    savings = estimate_savings(source, "python")
    assert isinstance(savings, float)
    assert 0.0 <= savings <= 1.0

