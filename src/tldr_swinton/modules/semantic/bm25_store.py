"""BM25 lexical search store for hybrid retrieval.

Stores a BM25 index alongside the FAISS vector index for hybrid search
using Reciprocal Rank Fusion (RRF).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Simple code-aware tokenizer.

    Splits on whitespace and punctuation, handles camelCase and snake_case,
    and lowercases everything.
    """
    # Split camelCase: insertBefore -> insert Before
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # Split on non-alphanumeric
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return tokens


class BM25Store:
    """BM25 index for lexical code search."""

    INDEX_FILE = "bm25_corpus.json"

    def __init__(self, index_dir: Path):
        self.index_dir = index_dir
        self._bm25 = None
        self._corpus: list[list[str]] = []
        self._unit_ids: list[str] = []

    @property
    def index_path(self) -> Path:
        return self.index_dir / self.INDEX_FILE

    def build(self, unit_ids: list[str], texts: list[str]) -> None:
        """Build BM25 index from tokenized texts.

        Args:
            unit_ids: Corresponding unit IDs for each text
            texts: Raw text for each code unit (same text used for embeddings)
        """
        from rank_bm25 import BM25Okapi

        self._unit_ids = unit_ids
        self._corpus = [_tokenize(text) for text in texts]
        self._bm25 = BM25Okapi(self._corpus)

    def save(self) -> None:
        """Save corpus and unit IDs to disk (BM25 is rebuilt on load)."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "unit_ids": self._unit_ids,
            "corpus": self._corpus,
        }
        self.index_path.write_text(json.dumps(data))

    def load(self) -> bool:
        """Load BM25 index from disk.

        Returns:
            True if loaded successfully, False if no index exists.
        """
        if not self.index_path.exists():
            return False

        try:
            from rank_bm25 import BM25Okapi

            data = json.loads(self.index_path.read_text())
            self._unit_ids = data["unit_ids"]
            self._corpus = data["corpus"]

            if self._corpus:
                self._bm25 = BM25Okapi(self._corpus)

            return True
        except Exception as e:
            logger.warning("Failed to load BM25 index: %s", e)
            return False

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        """Search using BM25.

        Args:
            query: Search query
            k: Number of results

        Returns:
            List of (unit_id, score) tuples, highest scores first
        """
        if self._bm25 is None or not self._unit_ids:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)

        # Get top-k indices sorted by score descending
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]

        return [
            (self._unit_ids[i], float(scores[i]))
            for i in top_indices
            if scores[i] > 0
        ]
