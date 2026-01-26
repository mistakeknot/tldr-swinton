"""Tests for attention-weighted context pruning."""

import tempfile
from pathlib import Path

import pytest

from tldr_swinton.modules.core.attention_pruning import (
    AttentionTracker,
    PruningDecision,
    SliceUsage,
    UsageStats,
    create_attention_reranker,
)


class TestAttentionTracker:
    def test_init_creates_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            assert tracker.db_path.exists()

    def test_record_delivery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            tracker.record_delivery("session-1", ["sym:a", "sym:b", "sym:c"])

            stats_a = tracker.get_usage_stats("sym:a")
            assert stats_a is not None
            assert stats_a.times_delivered == 1
            assert stats_a.times_used == 0

    def test_record_usage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            tracker.record_delivery("session-1", ["sym:a", "sym:b"])
            tracker.record_usage("session-1", ["sym:a"], "tool_call", "Bash")

            stats_a = tracker.get_usage_stats("sym:a")
            assert stats_a is not None
            assert stats_a.times_used == 1
            assert stats_a.usage_rate == 1.0
            assert "tool_call" in stats_a.common_use_types

            stats_b = tracker.get_usage_stats("sym:b")
            assert stats_b is not None
            assert stats_b.times_used == 0
            assert stats_b.usage_rate == 0.0

    def test_cooccurrence_tracking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            # Use symbols together multiple times
            for _ in range(5):
                tracker.record_delivery("session-1", ["sym:a", "sym:b"])
                tracker.record_usage("session-1", ["sym:a", "sym:b"], "edit")

            cooccur = tracker.get_cooccurring_symbols("sym:a")
            assert len(cooccur) == 1
            assert cooccur[0][0] == "sym:b"
            assert cooccur[0][1] == 5

    def test_compute_attention_score_no_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            score = tracker.compute_attention_score("unknown:symbol")

            # Should return neutral score for unknown symbols
            assert score == 0.5

    def test_compute_attention_score_with_usage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            # Symbol used 80% of the time
            for i in range(10):
                tracker.record_delivery("session-1", ["sym:a"])
                if i < 8:
                    tracker.record_usage("session-1", ["sym:a"], "edit")

            score = tracker.compute_attention_score("sym:a")
            assert score > 0.5  # Should be above neutral

    def test_compute_attention_score_unused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            # Symbol never used
            for _ in range(10):
                tracker.record_delivery("session-1", ["sym:a"])

            score = tracker.compute_attention_score("sym:a")
            assert score < 0.5  # Should be below neutral

    def test_prune_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            # Create history: sym:a used often, sym:b never
            for _ in range(10):
                tracker.record_delivery("session-1", ["sym:a", "sym:b"])
                tracker.record_usage("session-1", ["sym:a"], "edit")

            decisions = tracker.prune_candidates(
                candidates=["sym:a", "sym:b", "sym:c"],
                budget=2,
                min_score=0.3,
            )

            assert len(decisions) == 3

            # sym:a should be included (high usage)
            decision_a = next(d for d in decisions if d.symbol_id == "sym:a")
            assert decision_a.include is True

            # sym:b should be excluded (low score)
            decision_b = next(d for d in decisions if d.symbol_id == "sym:b")
            assert decision_b.include is False

    def test_prune_candidates_budget_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            # All symbols have neutral score
            decisions = tracker.prune_candidates(
                candidates=["sym:a", "sym:b", "sym:c", "sym:d"],
                budget=2,
                min_score=0.0,  # Accept all scores
            )

            included = [d for d in decisions if d.include]
            excluded = [d for d in decisions if not d.include]

            assert len(included) == 2
            assert len(excluded) == 2
            assert any("budget" in d.reason for d in excluded)

    def test_get_session_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            tracker.record_delivery("session-1", ["sym:a", "sym:b", "sym:c"])
            tracker.record_usage("session-1", ["sym:a"], "edit")
            tracker.record_usage("session-1", ["sym:b"], "tool_call")

            summary = tracker.get_session_summary("session-1")

            assert summary["slices_delivered"] == 3
            assert summary["slices_used"] == 2
            assert summary["usage_rate"] == pytest.approx(2 / 3)
            assert "edit" in summary["use_types"]
            assert "tool_call" in summary["use_types"]

    def test_cleanup_old_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            tracker.record_delivery("session-1", ["sym:a"])

            # Cleanup with 0 days (delete all)
            # Note: This won't delete today's data due to date comparison
            result = tracker.cleanup_old_data(days=0)
            assert "deliveries_deleted" in result


class TestUsageStats:
    def test_to_dict(self):
        stats = UsageStats(
            symbol_id="test:func",
            times_delivered=10,
            times_used=8,
            usage_rate=0.8,
            last_used="2025-01-25T10:00:00Z",
            common_use_types=["edit", "tool_call"],
        )

        d = stats.to_dict()

        assert d["symbol_id"] == "test:func"
        assert d["usage_rate"] == 0.8
        assert len(d["common_use_types"]) == 2


class TestCreateAttentionReranker:
    def test_reranker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            tracker = AttentionTracker(project)

            # Create history
            for _ in range(5):
                tracker.record_delivery("session-1", ["sym:high", "sym:low"])
                tracker.record_usage("session-1", ["sym:high"], "edit")

            reranker = create_attention_reranker(tracker)

            candidates = [
                {"symbol_id": "sym:low", "relevance": 0.9},
                {"symbol_id": "sym:high", "relevance": 0.5},
            ]

            reranked = reranker(candidates)

            # Despite lower relevance, sym:high should rank higher
            # due to attention boost
            assert reranked[0]["symbol_id"] == "sym:high"
            assert "attention_score" in reranked[0]
            assert "combined_score" in reranked[0]
