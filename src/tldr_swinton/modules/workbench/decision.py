"""Decision: Explicit choices with rationale.

A decision records an explicit choice made during development, with optional
rationale and links to the code symbols it affects. Decisions are stable
artifacts (low churn) that answer "why did we choose X?".
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone


def generate_decision_id() -> str:
    """Generate a short random decision ID.

    Returns:
        ID in format 'dec-xxxxxx' (6 hex chars).
    """
    return f"dec-{secrets.token_hex(3)}"


@dataclass
class Decision:
    """An explicit choice with rationale."""

    id: str
    statement: str
    reason: str | None
    refs: list[str]  # Symbol IDs this affects
    created_at: datetime
    superseded_by: str | None = None

    @classmethod
    def create(
        cls,
        statement: str,
        reason: str | None = None,
        refs: list[str] | None = None,
    ) -> Decision:
        """Create a new decision.

        Args:
            statement: The decision statement (what was decided).
            reason: Optional rationale (why it was decided).
            refs: Optional list of symbol IDs this affects.

        Returns:
            New Decision instance.
        """
        return cls(
            id=generate_decision_id(),
            statement=statement,
            reason=reason,
            refs=refs or [],
            created_at=datetime.now(timezone.utc),
            superseded_by=None,
        )

    @classmethod
    def from_dict(cls, data: dict) -> Decision:
        """Create Decision from database dict."""
        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            id=data["id"],
            statement=data["statement"],
            reason=data.get("reason"),
            refs=data.get("refs", []),
            created_at=created_at,
            superseded_by=data.get("superseded_by"),
        )

    @property
    def is_active(self) -> bool:
        """Check if decision is still active (not superseded)."""
        return self.superseded_by is None

    def format_short(self) -> str:
        """Format for brief display."""
        status = "" if self.is_active else " [superseded]"
        return f"{self.id}: {self.statement}{status}"


def parse_refs(refs_str: str | None) -> list[str]:
    """Parse comma-separated symbol refs.

    Args:
        refs_str: Comma-separated string like "db.py:get_conn,db.py:Pool"

    Returns:
        List of symbol IDs.
    """
    if not refs_str:
        return []
    return [r.strip() for r in refs_str.split(",") if r.strip()]
