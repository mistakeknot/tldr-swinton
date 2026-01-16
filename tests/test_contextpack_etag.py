from pathlib import Path

from tldr_swinton.contextpack_engine import Candidate, ContextPackEngine
from tldr_swinton.symbol_registry import SymbolRegistry


def test_contextpack_etag_changes_with_content(tmp_path: Path) -> None:
    file_path = tmp_path / "mod.py"
    file_path.write_text("def foo():\n    return 1\n")

    registry = SymbolRegistry(tmp_path, language="python")
    engine = ContextPackEngine(registry=registry)
    pack = engine.build_context_pack([Candidate("mod.py:foo", relevance=1)], budget_tokens=200)
    first_etag = pack.slices[0].etag

    file_path.write_text("def foo():\n    return 2\n")
    pack_updated = engine.build_context_pack([Candidate("mod.py:foo", relevance=1)], budget_tokens=200)
    second_etag = pack_updated.slices[0].etag

    assert first_etag is not None
    assert second_etag is not None
    assert first_etag != second_etag
