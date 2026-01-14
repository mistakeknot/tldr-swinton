from pathlib import Path

from tldr_swinton.api import get_relevant_context


def test_context_symbol_id_disambiguation(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "pkg" / "b.py").write_text("def foo():\n    return 2\n")

    ctx = get_relevant_context(tmp_path, "foo", depth=0)
    names = {f.name for f in ctx.functions}

    assert "pkg/a.py:foo" in names
    assert "pkg/b.py:foo" in names
