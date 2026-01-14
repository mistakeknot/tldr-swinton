from pathlib import Path

from tldr_swinton.api import search


def test_search_respects_tldrsignore(tmp_path: Path) -> None:
    (tmp_path / ".tldrsignore").write_text("ignored/\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "skip.py").write_text("def skip():\n    pass\n")
    (tmp_path / "keep.py").write_text("def keep():\n    pass\n")

    results = search("def", tmp_path, extensions={".py"})
    files = {r["file"] for r in results}
    assert "keep.py" in files
    assert "ignored/skip.py" not in files
