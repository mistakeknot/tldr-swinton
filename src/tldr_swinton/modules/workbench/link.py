"""Link: Typed relationships between artifacts.

Links form a graph connecting capsules, decisions, hypotheses, symbols,
and external artifacts (patches, tasks).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class ArtifactType(str, Enum):
    """Types of artifacts that can be linked."""

    CAPSULE = "capsule"
    DECISION = "decision"
    HYPOTHESIS = "hypothesis"
    SYMBOL = "symbol"  # Code symbol (e.g., "api.py:validate")
    PATCH = "patch"  # Git commit/patch
    TASK = "task"  # External task ID (e.g., Beads)


class LinkRelation(str, Enum):
    """Types of relationships between artifacts."""

    EVIDENCE = "evidence"  # Supports a decision/hypothesis
    FALSIFIES = "falsifies"  # Contradicts a hypothesis
    IMPLEMENTS = "implements"  # Patch implements a decision
    REFS = "refs"  # References a symbol
    SUPERSEDES = "supersedes"  # Replaces an older artifact
    RELATED = "related"  # General association


@dataclass
class Link:
    """A typed relationship between two artifacts."""

    src_id: str
    src_type: ArtifactType
    dst_id: str
    dst_type: ArtifactType
    relation: LinkRelation
    created_at: datetime

    @classmethod
    def create(
        cls,
        src_id: str,
        src_type: ArtifactType | str,
        dst_id: str,
        dst_type: ArtifactType | str,
        relation: LinkRelation | str,
    ) -> Link:
        """Create a new link.

        Args:
            src_id: Source artifact ID.
            src_type: Source artifact type.
            dst_id: Destination artifact ID.
            dst_type: Destination artifact type.
            relation: Relationship type.

        Returns:
            New Link instance.
        """
        if isinstance(src_type, str):
            src_type = ArtifactType(src_type)
        if isinstance(dst_type, str):
            dst_type = ArtifactType(dst_type)
        if isinstance(relation, str):
            relation = LinkRelation(relation)

        return cls(
            src_id=src_id,
            src_type=src_type,
            dst_id=dst_id,
            dst_type=dst_type,
            relation=relation,
            created_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_dict(cls, data: dict) -> Link:
        """Create Link from database dict."""
        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            src_id=data["src_id"],
            src_type=ArtifactType(data["src_type"]),
            dst_id=data["dst_id"],
            dst_type=ArtifactType(data["dst_type"]),
            relation=LinkRelation(data["relation"]),
            created_at=created_at,
        )

    def to_dict(self) -> dict:
        """Convert to dict for storage."""
        return {
            "src_id": self.src_id,
            "src_type": self.src_type.value,
            "dst_id": self.dst_id,
            "dst_type": self.dst_type.value,
            "relation": self.relation.value,
            "created_at": self.created_at.isoformat(),
        }

    def format_short(self) -> str:
        """Format for brief display."""
        return (
            f"{self.src_type.value}:{self.src_id} --{self.relation.value}--> "
            f"{self.dst_type.value}:{self.dst_id}"
        )


def parse_artifact_id(ref: str) -> tuple[str, ArtifactType]:
    """Parse an artifact reference into (id, type).

    Args:
        ref: Reference like 'capsule:abc123', 'dec-xyz', 'hyp-123', 'bd-task'.

    Returns:
        Tuple of (artifact_id, artifact_type).
    """
    if ref.startswith("capsule:"):
        return (ref[8:], ArtifactType.CAPSULE)
    elif ref.startswith("decision:"):
        return (ref[9:], ArtifactType.DECISION)
    elif ref.startswith("hypothesis:"):
        return (ref[11:], ArtifactType.HYPOTHESIS)
    elif ref.startswith("symbol:"):
        return (ref[7:], ArtifactType.SYMBOL)
    elif ref.startswith("patch:"):
        return (ref[6:], ArtifactType.PATCH)
    elif ref.startswith("task:"):
        return (ref[5:], ArtifactType.TASK)
    elif ref.startswith("dec-"):
        return (ref, ArtifactType.DECISION)
    elif ref.startswith("hyp-"):
        return (ref, ArtifactType.HYPOTHESIS)
    elif ref.startswith("bd-"):
        return (ref, ArtifactType.TASK)
    elif ":" in ref and "/" in ref.split(":")[0]:
        # Looks like a symbol (file:symbol format)
        return (ref, ArtifactType.SYMBOL)
    else:
        # Default to capsule
        return (ref, ArtifactType.CAPSULE)


def format_artifact_ref(artifact_id: str, artifact_type: ArtifactType) -> str:
    """Format an artifact as a reference string.

    Args:
        artifact_id: The artifact ID.
        artifact_type: The artifact type.

    Returns:
        Formatted reference like 'capsule:abc123'.
    """
    # For IDs that already include the type prefix, return as-is
    if artifact_type == ArtifactType.DECISION and artifact_id.startswith("dec-"):
        return artifact_id
    if artifact_type == ArtifactType.HYPOTHESIS and artifact_id.startswith("hyp-"):
        return artifact_id
    if artifact_type == ArtifactType.TASK and artifact_id.startswith("bd-"):
        return artifact_id

    return f"{artifact_type.value}:{artifact_id}"
