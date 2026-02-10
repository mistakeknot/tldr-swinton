"""Attention-Weighted Context Pruning via runtime feedback.

This module provides a feedback loop that learns from agent behavior to
improve retrieval ranking. It tracks which context slices lead to actual
tool calls/edits and uses this signal to prune unused context in future
retrievals.

Key features:
1. Track which slices lead to tool calls/edits (in session state)
2. Build lightweight usage model per-repo
3. Adjust retrieval ranking based on historical usage

Expected impact: 30-40% improvement in retrieval precision over time.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class SliceUsage:
    """Record of how a slice was used in a session."""

    symbol_id: str
    session_id: str
    delivered_at: str
    used: bool = False
    use_type: str | None = None  # tool_call, edit, reference, none
    use_context: str | None = None  # Additional context about usage


@dataclass
class UsageStats:
    """Aggregated usage statistics for a symbol."""

    symbol_id: str
    times_delivered: int
    times_used: int
    usage_rate: float
    last_used: str | None
    common_use_types: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "times_delivered": self.times_delivered,
            "times_used": self.times_used,
            "usage_rate": round(self.usage_rate, 3),
            "last_used": self.last_used,
            "common_use_types": self.common_use_types,
        }


@dataclass
class PruningDecision:
    """Decision about whether to include a symbol in context."""

    symbol_id: str
    include: bool
    score: float
    reason: str


class AttentionTracker:
    """Tracks and learns from context usage patterns."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.db_path = self.project_root / ".tldrs" / "attention.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _init_db(self) -> None:
        with self._conn() as conn:
            # Track deliveries and their outcomes
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS slice_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    symbol_id TEXT NOT NULL,
                    delivered_at TEXT NOT NULL,
                    used INTEGER DEFAULT 0,
                    use_type TEXT,
                    use_context TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_slice_symbol ON slice_deliveries(symbol_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_slice_session ON slice_deliveries(session_id)"
            )

            # Aggregated usage patterns
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_usage_stats (
                    symbol_id TEXT PRIMARY KEY,
                    times_delivered INTEGER DEFAULT 0,
                    times_used INTEGER DEFAULT 0,
                    last_delivered TEXT,
                    last_used TEXT,
                    use_type_counts TEXT DEFAULT '{}'
                )
                """
            )

            # Co-occurrence patterns (which symbols are used together)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_cooccurrence (
                    symbol_a TEXT NOT NULL,
                    symbol_b TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY(symbol_a, symbol_b)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS global_popularity (
                    symbol_id TEXT PRIMARY KEY,
                    delivery_count INTEGER DEFAULT 0,
                    usage_count INTEGER DEFAULT 0,
                    last_delivered TEXT,
                    last_used TEXT,
                    popularity_score REAL DEFAULT 0.0
                )
                """
            )

    def record_delivery(
        self,
        session_id: str,
        symbol_ids: list[str],
    ) -> None:
        """Record that symbols were delivered to the agent."""
        now = self._now()
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO slice_deliveries (session_id, symbol_id, delivered_at)
                VALUES (?, ?, ?)
                """,
                [(session_id, sid, now) for sid in symbol_ids],
            )

            # Update stats
            for symbol_id in symbol_ids:
                conn.execute(
                    """
                    INSERT INTO symbol_usage_stats (symbol_id, times_delivered, last_delivered)
                    VALUES (?, 1, ?)
                    ON CONFLICT(symbol_id) DO UPDATE SET
                        times_delivered = times_delivered + 1,
                        last_delivered = excluded.last_delivered
                    """,
                    (symbol_id, now),
                )

    def record_usage(
        self,
        session_id: str,
        symbol_ids: list[str],
        use_type: str,
        use_context: str | None = None,
    ) -> None:
        """Record that symbols were actually used by the agent.

        Args:
            session_id: Current session ID
            symbol_ids: Symbols that were used
            use_type: Type of use (tool_call, edit, reference)
            use_context: Additional context (e.g., tool name, edit type)
        """
        now = self._now()
        with self._conn() as conn:
            # Update recent deliveries for these symbols
            for symbol_id in symbol_ids:
                conn.execute(
                    """
                    UPDATE slice_deliveries
                    SET used = 1, use_type = ?, use_context = ?
                    WHERE session_id = ? AND symbol_id = ?
                    AND id = (
                        SELECT MAX(id) FROM slice_deliveries
                        WHERE session_id = ? AND symbol_id = ?
                    )
                    """,
                    (use_type, use_context, session_id, symbol_id, session_id, symbol_id),
                )

                # Update stats
                conn.execute(
                    """
                    UPDATE symbol_usage_stats
                    SET times_used = times_used + 1,
                        last_used = ?,
                        use_type_counts = json_set(
                            use_type_counts,
                            '$.' || ?,
                            COALESCE(json_extract(use_type_counts, '$.' || ?), 0) + 1
                        )
                    WHERE symbol_id = ?
                    """,
                    (now, use_type, use_type, symbol_id),
                )

            # Record co-occurrences
            if len(symbol_ids) > 1:
                for i, a in enumerate(symbol_ids):
                    for b in symbol_ids[i + 1 :]:
                        key = tuple(sorted([a, b]))
                        conn.execute(
                            """
                            INSERT INTO symbol_cooccurrence (symbol_a, symbol_b, count)
                            VALUES (?, ?, 1)
                            ON CONFLICT(symbol_a, symbol_b) DO UPDATE SET
                                count = count + 1
                            """,
                            key,
                        )

    def get_usage_stats(self, symbol_id: str) -> UsageStats | None:
        """Get usage statistics for a symbol."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT symbol_id, times_delivered, times_used, last_delivered, last_used, use_type_counts
                FROM symbol_usage_stats
                WHERE symbol_id = ?
                """,
                (symbol_id,),
            ).fetchone()

        if not row:
            return None

        times_delivered = row[1] or 0
        times_used = row[2] or 0
        usage_rate = times_used / max(1, times_delivered)

        try:
            use_type_counts = json.loads(row[5] or "{}")
        except json.JSONDecodeError:
            use_type_counts = {}

        common_types = sorted(use_type_counts.keys(), key=lambda k: use_type_counts[k], reverse=True)

        return UsageStats(
            symbol_id=row[0],
            times_delivered=times_delivered,
            times_used=times_used,
            usage_rate=usage_rate,
            last_used=row[4],
            common_use_types=common_types[:3],
        )

    def get_cooccurring_symbols(self, symbol_id: str, limit: int = 10) -> list[tuple[str, int]]:
        """Get symbols that frequently co-occur with the given symbol."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    CASE WHEN symbol_a = ? THEN symbol_b ELSE symbol_a END as other,
                    count
                FROM symbol_cooccurrence
                WHERE symbol_a = ? OR symbol_b = ?
                ORDER BY count DESC
                LIMIT ?
                """,
                (symbol_id, symbol_id, symbol_id, limit),
            ).fetchall()

        return [(row[0], row[1]) for row in rows]

    def update_global_popularity(self, session_id: str) -> None:
        """Aggregate one session's deliveries/usages into global popularity."""
        with self._conn() as conn:
            delivered = conn.execute(
                """
                SELECT symbol_id, COUNT(*), MAX(delivered_at)
                FROM slice_deliveries
                WHERE session_id = ?
                GROUP BY symbol_id
                """,
                (session_id,),
            ).fetchall()

            used = conn.execute(
                """
                SELECT symbol_id, COUNT(*), MAX(delivered_at)
                FROM slice_deliveries
                WHERE session_id = ? AND used = 1
                GROUP BY symbol_id
                """,
                (session_id,),
            ).fetchall()

            for symbol_id, count, last_delivered in delivered:
                conn.execute(
                    """
                    INSERT INTO global_popularity (symbol_id, delivery_count, last_delivered)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol_id) DO UPDATE SET
                        delivery_count = global_popularity.delivery_count + excluded.delivery_count,
                        last_delivered = CASE
                            WHEN global_popularity.last_delivered IS NULL THEN excluded.last_delivered
                            WHEN excluded.last_delivered > global_popularity.last_delivered THEN excluded.last_delivered
                            ELSE global_popularity.last_delivered
                        END
                    """,
                    (symbol_id, int(count or 0), last_delivered),
                )

            for symbol_id, count, last_used in used:
                conn.execute(
                    """
                    INSERT INTO global_popularity (symbol_id, usage_count, last_used)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol_id) DO UPDATE SET
                        usage_count = global_popularity.usage_count + excluded.usage_count,
                        last_used = CASE
                            WHEN global_popularity.last_used IS NULL THEN excluded.last_used
                            WHEN excluded.last_used > global_popularity.last_used THEN excluded.last_used
                            ELSE global_popularity.last_used
                        END
                    """,
                    (symbol_id, int(count or 0), last_used),
                )

            rows = conn.execute(
                """
                SELECT symbol_id, delivery_count, usage_count, last_used
                FROM global_popularity
                """
            ).fetchall()

            now = datetime.now(timezone.utc)
            for symbol_id, delivery_count, usage_count, last_used in rows:
                deliveries = max(int(delivery_count or 0), 1)
                usages = int(usage_count or 0)

                usage_rate = usages / deliveries

                recency_factor = 0.0
                if last_used:
                    try:
                        last_used_dt = datetime.fromisoformat(last_used)
                        if last_used_dt.tzinfo is None:
                            last_used_dt = last_used_dt.replace(tzinfo=timezone.utc)
                        days_since = max(
                            0.0,
                            (now - last_used_dt).total_seconds() / 86400.0,
                        )
                        recency_factor = 1.0 / (1.0 + days_since)
                    except Exception:
                        recency_factor = 0.0

                delivery_frequency = min((int(delivery_count or 0) / 50.0), 1.0)
                popularity_score = (
                    0.6 * usage_rate
                    + 0.3 * recency_factor
                    + 0.1 * delivery_frequency
                )

                conn.execute(
                    """
                    UPDATE global_popularity
                    SET popularity_score = ?
                    WHERE symbol_id = ?
                    """,
                    (float(popularity_score), symbol_id),
                )

    def get_global_popularity(self, symbol_ids: list[str]) -> dict[str, float]:
        """Return global popularity scores for symbols; missing symbols are 0.0."""
        if not symbol_ids:
            return {}

        scores = {symbol_id: 0.0 for symbol_id in symbol_ids}
        placeholders = ",".join("?" for _ in symbol_ids)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT symbol_id, popularity_score
                FROM global_popularity
                WHERE symbol_id IN ({placeholders})
                """,
                symbol_ids,
            ).fetchall()

        for symbol_id, popularity_score in rows:
            scores[symbol_id] = float(popularity_score or 0.0)
        return scores

    def get_hotspots(self, top_n: int = 20, since_days: int | None = None) -> list[dict]:
        """Return top symbols by global popularity score."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT symbol_id, delivery_count, usage_count, popularity_score, last_delivered, last_used
                FROM global_popularity
                ORDER BY popularity_score DESC
                """
            ).fetchall()

        if since_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
            filtered = []
            for row in rows:
                last_delivered = row[4]
                if not last_delivered:
                    continue
                try:
                    delivered_dt = datetime.fromisoformat(last_delivered)
                    if delivered_dt.tzinfo is None:
                        delivered_dt = delivered_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if delivered_dt >= cutoff:
                    filtered.append(row)
            rows = filtered

        limit = max(0, int(top_n))
        rows = rows[:limit]
        return [
            {
                "symbol_id": row[0],
                "delivery_count": int(row[1] or 0),
                "usage_count": int(row[2] or 0),
                "popularity_score": float(row[3] or 0.0),
                "last_delivered": row[4],
                "last_used": row[5],
            }
            for row in rows
        ]

    def compute_attention_score(self, symbol_id: str) -> float:
        """Compute attention score for a symbol based on historical usage.

        Higher scores mean the symbol is more likely to be useful.
        Score range: 0.0 to 1.0
        """
        stats = self.get_usage_stats(symbol_id)

        if stats is None:
            # No history - use neutral score
            session_score = 0.5
        else:
            # Base score from usage rate
            base_score = stats.usage_rate

            # Boost for recently used symbols
            recency_boost = 0.0
            if stats.last_used:
                try:
                    last_used = datetime.fromisoformat(stats.last_used)
                    age_hours = (datetime.now(timezone.utc) - last_used).total_seconds() / 3600
                    if age_hours < 1:
                        recency_boost = 0.2
                    elif age_hours < 24:
                        recency_boost = 0.1
                except Exception:
                    pass

            # Boost for frequently co-occurring symbols
            cooccur_boost = 0.0
            cooccurrences = self.get_cooccurring_symbols(symbol_id, limit=3)
            if cooccurrences:
                total_cooccur = sum(count for _, count in cooccurrences)
                if total_cooccur > 5:
                    cooccur_boost = min(0.1, total_cooccur / 100)

            # Session-specific score
            session_score = min(1.0, base_score + recency_boost + cooccur_boost)

        global_score = self.get_global_popularity([symbol_id]).get(symbol_id, 0.0)
        with self._conn() as conn:
            has_global_data = (
                conn.execute(
                    "SELECT 1 FROM global_popularity WHERE symbol_id = ? LIMIT 1",
                    (symbol_id,),
                ).fetchone()
                is not None
            )

        if has_global_data:
            return 0.7 * session_score + 0.3 * global_score
        return session_score

    def prune_candidates(
        self,
        candidates: list[str],
        budget: int,
        min_score: float = 0.3,
    ) -> list[PruningDecision]:
        """Decide which candidates to include based on attention scores.

        Args:
            candidates: List of symbol IDs being considered
            budget: Maximum number of symbols to include
            min_score: Minimum attention score to include

        Returns:
            List of PruningDecisions for each candidate
        """
        decisions: list[PruningDecision] = []

        # Score all candidates
        scored = []
        for symbol_id in candidates:
            score = self.compute_attention_score(symbol_id)
            scored.append((symbol_id, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        # Make decisions
        included = 0
        for symbol_id, score in scored:
            if included >= budget:
                decisions.append(
                    PruningDecision(
                        symbol_id=symbol_id,
                        include=False,
                        score=score,
                        reason="budget_exceeded",
                    )
                )
            elif score < min_score:
                decisions.append(
                    PruningDecision(
                        symbol_id=symbol_id,
                        include=False,
                        score=score,
                        reason=f"score_below_threshold ({score:.2f} < {min_score})",
                    )
                )
            else:
                decisions.append(
                    PruningDecision(
                        symbol_id=symbol_id,
                        include=True,
                        score=score,
                        reason="included",
                    )
                )
                included += 1

        return decisions

    def get_session_summary(self, session_id: str) -> dict[str, Any]:
        """Get summary of usage patterns for a session."""
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM slice_deliveries WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]

            used = conn.execute(
                "SELECT COUNT(*) FROM slice_deliveries WHERE session_id = ? AND used = 1",
                (session_id,),
            ).fetchone()[0]

            by_type = conn.execute(
                """
                SELECT use_type, COUNT(*)
                FROM slice_deliveries
                WHERE session_id = ? AND used = 1
                GROUP BY use_type
                """,
                (session_id,),
            ).fetchall()

        return {
            "session_id": session_id,
            "slices_delivered": total,
            "slices_used": used,
            "usage_rate": used / max(1, total),
            "use_types": {row[0]: row[1] for row in by_type if row[0]},
        }

    def cleanup_old_data(self, days: int = 30) -> dict[str, int]:
        """Clean up old delivery records to prevent database bloat."""
        cutoff = datetime.now(timezone.utc).isoformat()[:10]  # Just date

        with self._conn() as conn:
            # Delete old delivery records (keep stats)
            deleted = conn.execute(
                """
                DELETE FROM slice_deliveries
                WHERE delivered_at < date('now', '-' || ? || ' days')
                """,
                (days,),
            ).rowcount

        return {"deliveries_deleted": deleted}


def create_attention_reranker(
    tracker: AttentionTracker,
) -> callable:
    """Create a reranking function based on attention tracking.

    Returns a function that can be used to rerank retrieval results.
    """

    def rerank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rerank candidates based on attention scores.

        Each candidate should have a 'symbol_id' key.
        Returns candidates sorted by combined relevance and attention score.
        """
        for candidate in candidates:
            symbol_id = candidate.get("symbol_id", candidate.get("id", ""))
            attention_score = tracker.compute_attention_score(symbol_id)
            candidate["attention_score"] = attention_score

            # Combine with existing relevance score if present
            relevance = candidate.get("relevance", candidate.get("score", 0.5))
            # Weighted combination: 70% relevance, 30% attention
            candidate["combined_score"] = 0.7 * relevance + 0.3 * attention_score

        return sorted(candidates, key=lambda x: x.get("combined_score", 0), reverse=True)

    return rerank


def create_candidate_reranker(
    tracker: AttentionTracker,
) -> "Callable[[list[Candidate]], list[Candidate]]":
    """Create a post-processor that reranks Candidates using attention scores.

    Combines 70% original relevance + 30% attention score into a new
    relevance value, then re-sorts. Compatible with ContextPackEngine's
    post_processors parameter.
    """
    from .contextpack_engine import Candidate

    def rerank(candidates: list[Candidate]) -> list[Candidate]:
        scored: list[tuple[float, Candidate]] = []
        for candidate in candidates:
            attention = tracker.compute_attention_score(candidate.symbol_id)
            combined = 0.7 * candidate.relevance + 0.3 * attention
            scored.append((combined, candidate))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [c for _, c in scored]

    return rerank
