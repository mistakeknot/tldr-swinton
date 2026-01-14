from pathlib import Path

from tldr_swinton.api import get_relevant_context


def test_context_symbol_id_disambiguation(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "pkg" / "b.py").write_text("def foo():\n    return 2\n")

    ctx = get_relevant_context(tmp_path, "foo", depth=0)
    names = {f.name for f in ctx.functions}

    assert len(ctx.functions) == 1
    assert "pkg/a.py:foo" in names


def test_context_relative_project_resolves(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def foo():\n    return 1\n")

    monkeypatch.chdir(tmp_path)
    ctx = get_relevant_context(".", "pkg/a.py:foo", depth=0)

    assert len(ctx.functions) == 1
    func = ctx.functions[0]
    assert func.file.endswith("pkg/a.py")
    assert func.line == 1
