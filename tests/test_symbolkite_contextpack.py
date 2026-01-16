from pathlib import Path

from tldr_swinton.api import get_symbol_context_pack


def test_symbolkite_contextpack(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n")
    pack = get_symbol_context_pack(tmp_path, "foo", budget_tokens=50)
    assert pack["slices"]
