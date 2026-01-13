"""
Vector store abstraction for semantic search.

Supports FAISS for efficient similarity search with persistence.
"""

import json
import os
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

import numpy as np


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


@dataclass
class VectorStoreMetadata:
    """Metadata for a vector store."""
    version: str = "1.0"
    embed_model: str = ""
    embed_backend: str = ""
    dimension: int = 0
    count: int = 0
    project_root: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VectorStoreMetadata":
        # Handle missing fields gracefully
        known_fields = {"version", "embed_model", "embed_backend", "dimension", "count", "project_root"}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def make_unit_id(file: str, name: str, line: int) -> str:
    """Generate a stable ID for a code unit."""
    content = f"{file}:{name}:{line}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class VectorStore:
    """FAISS-backed vector store for code embeddings.

    Stores:
    - .tldr/index/vectors.faiss - FAISS index
    - .tldr/index/units.json - Code unit metadata
    - .tldr/index/meta.json - Store metadata
    """

    INDEX_DIR = ".tldr/index"

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.index_dir = self.project_root / self.INDEX_DIR

        self._index = None
        self._units: list[CodeUnit] = []
        self._id_to_idx: dict[str, int] = {}
        self._metadata = VectorStoreMetadata(project_root=str(self.project_root))

    @property
    def index_path(self) -> Path:
        return self.index_dir / "vectors.faiss"

    @property
    def units_path(self) -> Path:
        return self.index_dir / "units.json"

    @property
    def meta_path(self) -> Path:
        return self.index_dir / "meta.json"

    def exists(self) -> bool:
        """Check if a valid index exists."""
        return self.index_path.exists() and self.units_path.exists()

    def load(self) -> bool:
        """Load existing index from disk.

        Returns:
            True if loaded successfully, False if no index exists.
        """
        if not self.exists():
            return False

        try:
            import faiss

            # Load FAISS index
            self._index = faiss.read_index(str(self.index_path))

            # Load units
            units_data = json.loads(self.units_path.read_text())
            self._units = [CodeUnit.from_dict(u) for u in units_data]

            # Build ID lookup
            self._id_to_idx = {u.id: i for i, u in enumerate(self._units)}

            # Load metadata
            if self.meta_path.exists():
                self._metadata = VectorStoreMetadata.from_dict(
                    json.loads(self.meta_path.read_text())
                )

            return True
        except Exception as e:
            print(f"Warning: Failed to load index: {e}")
            return False

    def save(self) -> None:
        """Save index to disk."""
        import faiss

        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        if self._index is not None:
            faiss.write_index(self._index, str(self.index_path))

        # Save units
        units_data = [u.to_dict() for u in self._units]
        self.units_path.write_text(json.dumps(units_data, indent=2))

        # Update and save metadata
        self._metadata.count = len(self._units)
        self.meta_path.write_text(json.dumps(self._metadata.to_dict(), indent=2))

    def clear(self) -> None:
        """Clear the index."""
        self._index = None
        self._units = []
        self._id_to_idx = {}

        # Remove files
        if self.index_path.exists():
            self.index_path.unlink()
        if self.units_path.exists():
            self.units_path.unlink()
        if self.meta_path.exists():
            self.meta_path.unlink()

    def build(
        self,
        units: list[CodeUnit],
        embeddings: list[np.ndarray],
        embed_model: str = "",
        embed_backend: str = ""
    ) -> None:
        """Build index from units and their embeddings.

        Args:
            units: List of code units
            embeddings: Corresponding embedding vectors (must be same length)
            embed_model: Model used for embeddings
            embed_backend: Backend used (ollama/sentence-transformers)
        """
        import faiss

        if len(units) != len(embeddings):
            raise ValueError(f"Units ({len(units)}) and embeddings ({len(embeddings)}) count mismatch")

        if not embeddings:
            # Empty index
            self._units = []
            self._id_to_idx = {}
            self._index = None
            return

        # Stack embeddings
        matrix = np.vstack(embeddings).astype(np.float32)
        dimension = matrix.shape[1]

        # Build FAISS index (inner product for normalized vectors = cosine similarity)
        self._index = faiss.IndexFlatIP(dimension)
        self._index.add(matrix)

        # Store units and build lookup
        self._units = units
        self._id_to_idx = {u.id: i for i, u in enumerate(self._units)}

        # Update metadata
        self._metadata.dimension = dimension
        self._metadata.count = len(units)
        self._metadata.embed_model = embed_model
        self._metadata.embed_backend = embed_backend

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10
    ) -> list[SearchResult]:
        """Search for similar code units.

        Args:
            query_vector: Query embedding vector
            k: Number of results to return

        Returns:
            List of SearchResult objects, ranked by similarity
        """
        if self._index is None or not self._units:
            return []

        # Ensure correct shape
        query = query_vector.reshape(1, -1).astype(np.float32)

        # Search
        k = min(k, len(self._units))
        scores, indices = self._index.search(query, k)

        # Build results
        results = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx < 0 or idx >= len(self._units):
                continue
            results.append(SearchResult(
                unit=self._units[idx],
                score=float(score),
                rank=rank
            ))

        return results

    def get_unit(self, unit_id: str) -> Optional[CodeUnit]:
        """Get a unit by ID."""
        idx = self._id_to_idx.get(unit_id)
        if idx is not None:
            return self._units[idx]
        return None

    def get_units_by_file(self, file_path: str) -> list[CodeUnit]:
        """Get all units in a file."""
        # Normalize path
        rel_path = str(Path(file_path))
        return [u for u in self._units if u.file == rel_path]

    def get_units_by_name(self, name: str) -> list[CodeUnit]:
        """Get all units matching a name (exact match)."""
        return [u for u in self._units if u.name == name]

    def get_all_units(self) -> list[CodeUnit]:
        """Get all indexed units."""
        return list(self._units)

    def reconstruct_all_vectors(self) -> np.ndarray:
        """Reconstruct all embedding vectors from the FAISS index.

        Used for incremental updates - instead of re-embedding unchanged units,
        we can reconstruct their existing vectors from the index.

        Returns:
            (n, d) float32 matrix of all vectors, or empty array if no index
        """
        if self._index is None or not self._units:
            return np.zeros((0, 0), dtype=np.float32)

        try:
            # reconstruct_n is efficient for flat indexes
            return self._index.reconstruct_n(0, len(self._units))
        except Exception:
            # Fallback to per-vector reconstruction
            vectors = []
            for i in range(len(self._units)):
                vectors.append(self._index.reconstruct(i))
            return np.vstack(vectors).astype(np.float32)

    def get_vector(self, idx: int) -> Optional[np.ndarray]:
        """Reconstruct a single vector by index.

        Args:
            idx: Index of the vector in the FAISS index

        Returns:
            Vector as float32 array, or None if invalid
        """
        if self._index is None or idx < 0 or idx >= len(self._units):
            return None
        try:
            return self._index.reconstruct(idx).astype(np.float32)
        except Exception:
            return None

    @property
    def count(self) -> int:
        """Number of indexed units."""
        return len(self._units)

    @property
    def metadata(self) -> VectorStoreMetadata:
        """Index metadata."""
        return self._metadata


def get_file_hash(file_path: Path) -> str:
    """Compute hash of file content for change detection."""
    if not file_path.exists():
        return ""
    content = file_path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]
