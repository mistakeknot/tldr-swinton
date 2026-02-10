from textwrap import dedent

from tldr_swinton.modules.core.zoom import ZoomLevel, extract_body_sketch, format_at_zoom


def test_zoom_level_from_string() -> None:
    assert ZoomLevel.from_string("L0") is ZoomLevel.L0
    assert ZoomLevel.from_string("l2") is ZoomLevel.L2
    assert ZoomLevel.from_string("L4") is ZoomLevel.L4


def test_extract_body_sketch_python() -> None:
    source = dedent(
        """
        def sample(items):
            total = 0
            if items:
                for item in items:
                    total += item.value()
            return total
        """
    ).strip()

    sketch = extract_body_sketch(source, "python")

    assert "def sample(items)" in sketch
    assert "if" in sketch
    assert "for" in sketch
    assert "return" in sketch
    assert "total =" not in sketch
    assert "item.value()" not in sketch


def test_extract_body_sketch_preserves_indentation() -> None:
    source = dedent(
        """
        def nested(value):
            if value > 0:
                for n in range(value):
                    return n
            return 0
        """
    ).strip()

    sketch = extract_body_sketch(source, "python")
    lines = [line for line in sketch.splitlines() if line.strip()]
    if_line = next(line for line in lines if line.strip() == "if")
    for_line = next(line for line in lines if line.strip() == "for")
    return_line = next(line for line in lines if line.strip() == "return")

    assert if_line.startswith("    ")
    assert for_line.startswith("        ")
    assert return_line.startswith("            ")


def test_format_at_zoom_l0() -> None:
    assert format_at_zoom("a.py:foo", "def foo()", "print(1)", ZoomLevel.L0) == "a.py:foo"


def test_format_at_zoom_l1() -> None:
    out = format_at_zoom("a.py:foo", "def foo()", "print(1)", ZoomLevel.L1)
    assert out == "a.py:foo\ndef foo()"


def test_format_at_zoom_l2() -> None:
    code = dedent(
        """
        def foo(flag):
            if flag:
                return 1
            return 0
        """
    ).strip()
    out = format_at_zoom("a.py:foo", "def foo(flag)", code, ZoomLevel.L2, language="python")
    assert "a.py:foo" in out
    assert "def foo(flag)" in out
    assert "if" in out
    assert "return" in out


def test_format_at_zoom_l4() -> None:
    code = "def foo():\n    value = 1\n    return value"
    out = format_at_zoom("a.py:foo", "def foo()", code, ZoomLevel.L4, language="python")
    assert out == "a.py:foo\ndef foo()\ndef foo():\n    value = 1\n    return value"


def test_l2_smaller_than_l4() -> None:
    code = dedent(
        """
        def heavy(items):
            result = [item.transform(x=1, y=2, z=3) for item in items if item.enabled]
            if result:
                for value in result:
                    print(value.compute(alpha=123, beta=456, gamma=789))
            return sum(v.finalize(flag=True) for v in result)
        """
    ).strip()
    l2 = format_at_zoom("a.py:heavy", "def heavy(items)", code, ZoomLevel.L2, language="python")
    l4 = format_at_zoom("a.py:heavy", "def heavy(items)", code, ZoomLevel.L4, language="python")
    assert len(l2) <= int(len(l4) * 0.7)


def test_unsupported_language_falls_back() -> None:
    l1 = format_at_zoom("a.txt:foo", "foo()", "some code", ZoomLevel.L1, language="txt")
    l2 = format_at_zoom("a.txt:foo", "foo()", "some code", ZoomLevel.L2, language="txt")
    assert l2 == l1
