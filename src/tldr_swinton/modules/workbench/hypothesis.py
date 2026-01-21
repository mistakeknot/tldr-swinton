"""Hypothesis: Testable claims about system behavior.

A hypothesis records a testable claim with lifecycle (active → confirmed/falsified).
Hypotheses prevent circular debugging by tracking what was tried and why it was
ruled out.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class HypothesisStatus(str, Enum):
    """Hypothesis lifecycle status."""

    ACTIVE = "active"
    CONFIRMED = "confirmed"
    FALSIFIED = "falsified"


def generate_hypothesis_id() -> str:
    """Generate a short random hypothesis ID.

    Returns:
        ID in format 'hyp-xxxxxx' (6 hex chars).
    """
    return f"hyp-{secrets.token_hex(3)}"


@dataclass
class Hypothesis:
    """A testable claim about system behavior."""

    id: str
    statement: str
    status: HypothesisStatus
    test: str | None  # How to test it
    disconfirmer: str | None  # What would prove it wrong
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_note: str | None = None

    @classmethod
    def create(
        cls,
        statement: str,
        test: str | None = None,
        disconfirmer: str | None = None,
    ) -> Hypothesis:
        """Create a new active hypothesis.

        Args:
            statement: The hypothesis statement (the claim).
            test: Optional description of how to test it.
            disconfirmer: Optional description of what would prove it wrong.

        Returns:
            New Hypothesis instance with active status.
        """
        return cls(
            id=generate_hypothesis_id(),
            statement=statement,
            status=HypothesisStatus.ACTIVE,
            test=test,
            disconfirmer=disconfirmer,
            created_at=datetime.now(timezone.utc),
            resolved_at=None,
            resolution_note=None,
        )

    @classmethod
    def from_dict(cls, data: dict) -> Hypothesis:
        """Create Hypothesis from database dict."""
        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        resolved_at = data.get("resolved_at")
        if isinstance(resolved_at, str):
            resolved_at = datetime.fromisoformat(resolved_at)

        return cls(
            id=data["id"],
            statement=data["statement"],
            status=HypothesisStatus(data["status"]),
            test=data.get("test"),
            disconfirmer=data.get("disconfirmer"),
            created_at=created_at,
            resolved_at=resolved_at,
            resolution_note=data.get("resolution_note"),
        )

    @property
    def is_active(self) -> bool:
        """Check if hypothesis is still active."""
        return self.status == HypothesisStatus.ACTIVE

    @property
    def is_resolved(self) -> bool:
        """Check if hypothesis has been resolved."""
        return self.status in (HypothesisStatus.CONFIRMED, HypothesisStatus.FALSIFIED)

    def confirm(self, note: str | None = None) -> None:
        """Mark hypothesis as confirmed.

        Args:
            note: Optional resolution note.
        """
        self.status = HypothesisStatus.CONFIRMED
        self.resolved_at = datetime.now(timezone.utc)
        self.resolution_note = note

    def falsify(self, note: str | None = None) -> None:
        """Mark hypothesis as falsified.

        Args:
            note: Optional resolution note.
        """
        self.status = HypothesisStatus.FALSIFIED
        self.resolved_at = datetime.now(timezone.utc)
        self.resolution_note = note

    def format_short(self) -> str:
        """Format for brief display."""
        status_str = f" [{self.status.value}]" if self.is_resolved else ""
        return f"{self.id}: {self.statement}{status_str}"


@dataclass
class Evidence:
    """A link between a hypothesis and supporting/falsifying evidence."""

    hypothesis_id: str
    artifact_id: str
    artifact_type: str  # 'capsule', 'decision', etc.
    relation: str  # 'supports', 'falsifies'
    created_at: datetime

    @classmethod
    def create(
        cls,
        hypothesis_id: str,
        artifact_id: str,
        artifact_type: str,
        relation: str,
    ) -> Evidence:
        """Create a new evidence link."""
        return cls(
            hypothesis_id=hypothesis_id,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            relation=relation,
            created_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_dict(cls, data: dict) -> Evidence:
        """Create Evidence from database dict."""
        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            hypothesis_id=data["hypothesis_id"],
            artifact_id=data["artifact_id"],
            artifact_type=data["artifact_type"],
            relation=data["relation"],
            created_at=created_at,
        )


def parse_artifact_ref(ref: str) -> tuple[str, str]:
    """Parse an artifact reference into (type, id).

    Args:
        ref: Reference like 'capsule:abc123' or 'dec-abc123'.

    Returns:
        Tuple of (artifact_type, artifact_id).
    """
    if ref.startswith("capsule:"):
        return ("capsule", ref[8:])
    elif ref.startswith("dec-"):
        return ("decision", ref)
    elif ref.startswith("hyp-"):
        return ("hypothesis", ref)
    else:
        # Assume capsule ID without prefix
        return ("capsule", ref)
