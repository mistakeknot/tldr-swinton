from pathlib import Path

from tldr_swinton.contextpack_engine import Candidate, ContextPackEngine
from tldr_swinton.output_formats import _estimate_tokens
from tldr_swinton.symbol_registry import SymbolRegistry


def test_budget_allocates_full_then_signature(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def hi():\n    return 1\n")
    (tmp_path / "b.py").write_text("def lo():\n    return 2\n")
    registry = SymbolRegistry(tmp_path, language="python")
    engine = ContextPackEngine(registry=registry)
    first_full = _estimate_tokens("def hi()") + _estimate_tokens("def hi():\n    return 1\n")
    second_sig = _estimate_tokens("def lo()")
    budget = first_full + second_sig
    pack = engine.build_context_pack(
        [Candidate("a.py:hi", relevance=100), Candidate("b.py:lo", relevance=10)],
        budget_tokens=budget,
    )
    assert pack.slices[0].id.endswith("a.py:hi")
    assert "b.py:lo" in pack.signatures_only
