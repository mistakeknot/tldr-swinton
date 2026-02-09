"""Integration tests for attention_pruning wired into ContextPackEngine."""

from pathlib import Path

import pytest

from tldr_swinton.modules.core.attention_pruning import (
    AttentionTracker,
    create_candidate_reranker,
)
from tldr_swinton.modules.core.contextpack_engine import Candidate


@pytest.fixture
def tracker(tmp_path: Path) -> AttentionTracker:
    return AttentionTracker(tmp_path)


def _make_candidate(symbol_id: str, relevance: int) -> Candidate:
    return Candidate(
        symbol_id=symbol_id,
        relevance=relevance,
        relevance_label="test",
        order=0,
        signature=f"def {symbol_id.split(':')[-1]}()",
    )


class TestCandidateReranker:
    def test_reranker_preserves_order_without_history(self, tracker: AttentionTracker) -> None:
        """Without usage history, all symbols get neutral 0.5 attention score."""
        reranker = create_candidate_reranker(tracker)

        candidates = [
            _make_candidate("a.py:low", 1),
            _make_candidate("a.py:mid", 5),
            _make_candidate("a.py:high", 10),
        ]
        result = reranker(candidates)

        # Without history, order should be by original relevance (descending)
        assert result[0].symbol_id == "a.py:high"
        assert result[-1].symbol_id == "a.py:low"

    def test_reranker_boosts_frequently_used(self, tracker: AttentionTracker) -> None:
        """Symbols with high usage history should be ranked higher."""
        # Record heavy usage for "a.py:helper"
        for _ in range(10):
            tracker.record_delivery("s1", ["a.py:helper", "a.py:unused"])
            tracker.record_usage("s1", ["a.py:helper"], "tool_call")

        reranker = create_candidate_reranker(tracker)

        candidates = [
            _make_candidate("a.py:helper", 5),   # Same relevance but high attention
            _make_candidate("a.py:unused", 5),    # Same relevance but never used
        ]
        result = reranker(candidates)

        # "helper" should be boosted above "unused" due to attention score
        assert result[0].symbol_id == "a.py:helper"

    def test_reranker_returns_same_count(self, tracker: AttentionTracker) -> None:
        """Reranker should never add or remove candidates."""
        reranker = create_candidate_reranker(tracker)

        candidates = [_make_candidate(f"a.py:f{i}", i) for i in range(5)]
        result = reranker(candidates)
        assert len(result) == 5

    def test_reranker_handles_empty_list(self, tracker: AttentionTracker) -> None:
        reranker = create_candidate_reranker(tracker)
        assert reranker([]) == []
