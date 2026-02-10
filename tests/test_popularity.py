from datetime import datetime, timedelta, timezone

import pytest

from tldr_swinton.modules.core.attention_pruning import AttentionTracker


def test_update_global_popularity(tmp_path):
    tracker = AttentionTracker(tmp_path)

    tracker.record_delivery("s1", ["sym:a", "sym:b"])
    tracker.record_usage("s1", ["sym:a"], "edit")
    tracker.record_delivery("s2", ["sym:a", "sym:c"])
    tracker.record_usage("s2", ["sym:c"], "tool_call")

    tracker.update_global_popularity("s1")
    tracker.update_global_popularity("s2")

    with tracker._conn() as conn:
        rows = conn.execute(
            "SELECT symbol_id, delivery_count, usage_count FROM global_popularity"
        ).fetchall()

    by_symbol = {row[0]: (row[1], row[2]) for row in rows}
    assert by_symbol["sym:a"] == (2, 1)
    assert by_symbol["sym:b"] == (1, 0)
    assert by_symbol["sym:c"] == (1, 1)


def test_get_global_popularity_missing(tmp_path):
    tracker = AttentionTracker(tmp_path)
    tracker.record_delivery("s1", ["sym:a"])
    tracker.record_usage("s1", ["sym:a"], "edit")
    tracker.update_global_popularity("s1")

    scores = tracker.get_global_popularity(["sym:a", "sym:missing"])
    assert scores["sym:a"] > 0.0
    assert scores["sym:missing"] == 0.0


def test_get_hotspots_ordering(tmp_path):
    tracker = AttentionTracker(tmp_path)
    now = datetime.now(timezone.utc).isoformat()

    with tracker._conn() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO global_popularity
            (symbol_id, delivery_count, usage_count, last_delivered, last_used, popularity_score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("sym:high", 20, 18, now, now, 0.95),
                ("sym:mid", 20, 10, now, now, 0.60),
                ("sym:low", 20, 1, now, now, 0.15),
            ],
        )

    hotspots = tracker.get_hotspots(top_n=3)
    assert [row["symbol_id"] for row in hotspots] == ["sym:high", "sym:mid", "sym:low"]


def test_get_hotspots_since_filter(tmp_path):
    tracker = AttentionTracker(tmp_path)
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=40)).isoformat()

    with tracker._conn() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO global_popularity
            (symbol_id, delivery_count, usage_count, last_delivered, last_used, popularity_score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("sym:new", 10, 8, recent, recent, 0.70),
                ("sym:old", 10, 8, old, old, 0.90),
            ],
        )

    hotspots = tracker.get_hotspots(top_n=10, since_days=7)
    assert [row["symbol_id"] for row in hotspots] == ["sym:new"]


def test_cold_start_blending(tmp_path):
    tracker = AttentionTracker(tmp_path)
    tracker.record_delivery("s1", ["sym:cold"])

    score = tracker.compute_attention_score("sym:cold")
    assert score == pytest.approx(0.0)


def test_warm_blending(tmp_path):
    tracker = AttentionTracker(tmp_path)
    tracker.record_delivery("s1", ["sym:warm"])

    now = datetime.now(timezone.utc).isoformat()
    with tracker._conn() as conn:
        conn.execute(
            """
            INSERT INTO global_popularity
            (symbol_id, delivery_count, usage_count, last_delivered, last_used, popularity_score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("sym:warm", 50, 50, now, now, 1.0),
        )

    score = tracker.compute_attention_score("sym:warm")
    assert score == pytest.approx(0.3)
