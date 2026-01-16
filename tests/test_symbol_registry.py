from pathlib import Path

from tldr_swinton.symbol_registry import SymbolRegistry


def test_symbol_registry_resolves_signature(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("def foo(x):\n    return x\n")
    registry = SymbolRegistry(tmp_path, language="python")
    info = registry.get("mod.py:foo")
    assert info.signature.startswith("def foo")
