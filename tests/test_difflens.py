from pathlib import Path

from tldr_swinton.api import (
    build_diff_context_from_hunks,
    map_hunks_to_symbols,
    parse_unified_diff,
)


def test_parse_unified_diff_extracts_ranges() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n"
        "@@ -1,0 +1,2 @@\n"
        "+def foo():\n"
        "+    return 1\n"
    )
    hunks = parse_unified_diff(diff)
    assert hunks == [("a.py", 1, 2)]


def test_map_hunks_to_symbols(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def foo():\n"
        "    return 1\n"
        "\n"
        "def bar():\n"
        "    return 2\n"
    )
    hunks = [("a.py", 1, 2)]
    symbols = map_hunks_to_symbols(tmp_path, hunks, language="python")
    assert "a.py:foo" in symbols


def test_build_diff_context_from_hunks(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def bar():\n"
        "    return 2\n"
        "\n"
        "def foo():\n"
        "    return bar()\n"
    )
    hunks = [("a.py", 4, 5)]
    pack = build_diff_context_from_hunks(tmp_path, hunks, language="python", budget_tokens=500)

    ids = [item["id"] for item in pack["slices"]]
    assert "a.py:foo" in ids
    assert any(item["id"] == "a.py:bar" and item["relevance"] == "callee" for item in pack["slices"])
