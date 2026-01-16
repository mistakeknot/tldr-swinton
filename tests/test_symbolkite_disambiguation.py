from pathlib import Path

from tldr_swinton.api import get_symbol_context_pack


def test_symbolkite_disambiguation_returns_candidates(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def dup():\n    return 1\n")
    (tmp_path / "b.py").write_text("def dup():\n    return 2\n")

    pack = get_symbol_context_pack(tmp_path, "dup", budget_tokens=200)
    assert pack.get("ambiguous") is True
    assert len(pack.get("candidates", [])) == 2
