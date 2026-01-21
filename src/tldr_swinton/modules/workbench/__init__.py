"""
Workbench: Session artifacts for agent reasoning.

Tracks capsules (command executions), decisions, hypotheses, and their
relationships to support transparent agent reasoning.
"""

__version__ = "0.1.0"

from .capsule import Capsule, capture, replay_command
from .decision import Decision, parse_refs
from .hypothesis import Hypothesis
from .link import Link, ArtifactType, LinkRelation, parse_artifact_id, format_artifact_ref
from .store import WorkbenchStore

__all__ = [
    # Capsules
    "Capsule",
    "capture",
    "replay_command",
    # Decisions
    "Decision",
    "parse_refs",
    # Hypotheses
    "Hypothesis",
    # Links
    "Link",
    "ArtifactType",
    "LinkRelation",
    "parse_artifact_id",
    "format_artifact_ref",
    # Store
    "WorkbenchStore",
    # Version
    "__version__",
]
