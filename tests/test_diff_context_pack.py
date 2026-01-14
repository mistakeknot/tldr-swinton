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


def test_diff_context_pack_windows_code_around_diffs(tmp_path: Path) -> None:
    lines = ["def foo():"]
    for idx in range(1, 45):
        lines.append(f"    line{idx} = {idx}")
    lines.append("    return line44")
    (tmp_path / "mod.py").write_text("\n".join(lines) + "\n")

    hunks = [("mod.py", 3, 3), ("mod.py", 30, 30)]
    pack = build_diff_context_from_hunks(tmp_path, hunks)

    assert pack["slices"], "Expected at least one slice"
    code = pack["slices"][0].get("code")
    assert code is not None
    assert "..." in code
    assert "line2 = 2" in code
    assert "line29 = 29" in code
    assert "line10 = 10" not in code
