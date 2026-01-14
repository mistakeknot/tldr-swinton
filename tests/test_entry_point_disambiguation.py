from pathlib import Path

from tldr_swinton.api import get_relevant_context


def test_entry_point_disambiguates_to_single_symbol(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def run():\n    return 1\n")
    (tmp_path / "b.py").write_text("def run():\n    return 2\n")

    ctx = get_relevant_context(tmp_path, "run", depth=0)
    assert len(ctx.functions) == 1
    func = ctx.functions[0]
    assert func.file.endswith("a.py")
