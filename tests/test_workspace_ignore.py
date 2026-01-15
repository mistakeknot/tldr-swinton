from pathlib import Path

from tldr_swinton.engines.symbolkite import get_relevant_context


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_tldrsignore_excludes_files(tmp_path: Path) -> None:
    _write(tmp_path / ".tldrsignore", "ignored.py\n")
    _write(tmp_path / "ignored.py", "def ignored():\n    return 1\n")
    _write(tmp_path / "main.py", "def entry():\n    return 2\n")

    ctx = get_relevant_context(tmp_path, "entry", depth=1, language="python")
    names = [func.name for func in ctx.functions]
    assert all("ignored.py" not in name for name in names)
