from pathlib import Path

from tldr_swinton.api import get_code_structure


def test_structure_can_bypass_tldrsignore(tmp_path: Path) -> None:
    (tmp_path / ".tldrsignore").write_text("ignored/\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "skip.py").write_text("def skip():\n    pass\n")
    (tmp_path / "keep.py").write_text("def keep():\n    pass\n")

    result = get_code_structure(
        tmp_path,
        language="python",
        max_results=10,
        respect_ignore=False,
    )
    paths = {entry["path"] for entry in result["files"]}
    assert "keep.py" in paths
    assert "ignored/skip.py" in paths
