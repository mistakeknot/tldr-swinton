from tldr_swinton.contextpack_engine import Candidate, ContextPackEngine


def test_contextpack_orders_by_relevance_and_applies_budget() -> None:
    candidates = [
        Candidate("a.py:high", relevance=100),
        Candidate("b.py:low", relevance=10),
    ]
    engine = ContextPackEngine()
    pack = engine.build_context_pack(candidates, budget_tokens=50)
    assert pack.slices
    assert pack.slices[0].id.endswith("a.py:high")
