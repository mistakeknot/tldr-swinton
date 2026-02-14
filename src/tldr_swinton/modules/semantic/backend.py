"""
SearchBackend protocol and factory for semantic search backends.

Defines the shared abstraction for FAISS and ColBERT backends,
along with shared types (CodeUnit, SearchResult) and the factory
function that selects the right backend.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared domain types (moved from vector_store.py)
# ---------------------------------------------------------------------------


@dataclass
class CodeUnit:
    """A code unit (function/method/class) stored in the vector index.

    Minimal metadata for retrieval - full code is fetched on demand.
    """
    id: str  # Unique ID (hash of file:name:line)
    name: str  # Function/class name
    file: str  # Relative file path
    line: int  # Line number
    unit_type: str  # "function" | "method" | "class"
    signature: str  # Full signature
    language: str  # Programming language
    summary: str = ""  # One-line summary (from Ollama or docstring)

    # For incremental updates
    file_hash: str = ""  # Hash of file content when indexed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CodeUnit":
        return cls(**data)


@dataclass
class SearchResult:
    """A single search result."""
    unit: CodeUnit
    score: float
    rank: int


def make_unit_id(file: str, name: str, line: int) -> str:
    """Generate a stable ID for a code unit."""
    content = f"{file}:{name}:{line}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_file_hash(file_path: Path) -> str:
    """Compute hash of file content for change detection."""
    if not file_path.exists():
        return ""
    content = file_path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Backend protocol and stats
# ---------------------------------------------------------------------------


@dataclass
class BackendStats:
    """Statistics from a backend build operation."""
    total_units: int = 0
    new_units: int = 0
    updated_units: int = 0
    unchanged_units: int = 0
    embed_model: str = ""
    backend_name: str = ""


@dataclass
class BackendInfo:
    """Typed return for backend info() method."""
    backend_name: str
    model: str
    dimension: int  # For single-vector: vector dim; for ColBERT: token dim
    count: int
    index_path: str
    extra: dict = field(default_factory=dict)


@runtime_checkable
class SearchBackend(Protocol):
    """Protocol for semantic search backends.

    Both FAISSBackend and ColBERTBackend implement this interface.
    The backend handles its own embedding — build() takes raw text,
    not pre-computed vectors.
    """

    def build(
        self,
        units: list[CodeUnit],
        texts: list[str],
        *,
        rebuild: bool = False,
    ) -> BackendStats: ...

    def search(self, query: str, k: int = 10) -> list[SearchResult]: ...

    def load(self) -> bool: ...

    def save(self) -> None: ...

    def info(self) -> BackendInfo: ...


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Index metadata filename (shared across backends)
META_FILENAME = "meta.json"


def _colbert_available() -> bool:
    """Check if PyLate (ColBERT backend) is importable."""
    try:
        import pylate  # noqa: F401
        return True
    except ImportError:
        return False


def _faiss_available() -> bool:
    """Check if FAISS + numpy are importable."""
    try:
        import faiss  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def _read_index_backend(project_path: str) -> Optional[str]:
    """Read the backend name from an existing index's meta.json.

    Returns "faiss", "colbert", or None if no index/no backend field.
    """
    meta_path = Path(project_path).resolve() / ".tldrs" / "index" / META_FILENAME
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text())
        return meta.get("backend")
    except (json.JSONDecodeError, OSError):
        return None


def get_backend(project_path: str, backend: str = "auto") -> SearchBackend:
    """Get a search backend instance.

    Args:
        project_path: Path to project root.
        backend: "auto" | "colbert" | "faiss".
            - "auto": use existing index's backend if present, else try
              colbert (if pylate installed), then faiss.
            - "colbert": ColBERTBackend or error.
            - "faiss": FAISSBackend or error.

    Returns:
        A SearchBackend instance.

    Raises:
        RuntimeError: If requested backend's dependencies are missing.
    """
    if backend == "auto":
        # Respect the existing index's backend
        existing = _read_index_backend(project_path)
        if existing in ("faiss", "colbert"):
            backend = existing
        else:
            # No existing index — prefer colbert if available
            if _colbert_available():
                backend = "colbert"
            elif _faiss_available():
                backend = "faiss"
            else:
                raise RuntimeError(
                    "No search backend available. Install one of:\n"
                    "  pip install 'tldr-swinton[semantic-ollama]'  (FAISS)\n"
                    "  pip install 'tldr-swinton[semantic-colbert]' (ColBERT)"
                )

    if backend == "colbert":
        if not _colbert_available():
            raise RuntimeError(
                "ColBERT backend requires pylate. "
                "Install with: pip install 'tldr-swinton[semantic-colbert]'"
            )
        from .colbert_backend import ColBERTBackend
        return ColBERTBackend(project_path)

    if backend == "faiss":
        if not _faiss_available():
            raise RuntimeError(
                "FAISS backend requires numpy and faiss-cpu. "
                "Install with: pip install 'tldr-swinton[semantic-ollama]' "
                "or 'tldr-swinton[semantic]'"
            )
        from .faiss_backend import FAISSBackend
        return FAISSBackend(project_path)

    raise ValueError(f"Unknown backend: {backend!r}. Use 'auto', 'faiss', or 'colbert'.")
