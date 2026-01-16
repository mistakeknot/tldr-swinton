from pathlib import Path

from tldr_swinton.api import get_diff_context


def test_difflens_uses_contextpack_engine(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def hi():\n    return 1\n")
    pack = get_diff_context(tmp_path, budget_tokens=50)
    assert "slices" in pack
