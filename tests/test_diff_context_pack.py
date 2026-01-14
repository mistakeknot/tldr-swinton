from pathlib import Path

from tldr_swinton.api import build_diff_context_from_hunks


def test_diff_context_pack_omits_signatures_only(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        """

def foo():
    a = 1
    b = 2
    c = 3
    return c
""".lstrip()
    )

    hunks = [("mod.py", 2, 4)]
    pack = build_diff_context_from_hunks(tmp_path, hunks)

    assert "signatures_only" not in pack


def test_diff_context_pack_range_encodes_diff_lines(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        """

def foo():
    a = 1
    b = 2
    c = 3
    return c
""".lstrip()
    )

    hunks = [("mod.py", 2, 4)]
    pack = build_diff_context_from_hunks(tmp_path, hunks)

    assert pack["slices"], "Expected at least one slice"
    diff_lines = pack["slices"][0].get("diff_lines")
    assert diff_lines == [[2, 4]]
