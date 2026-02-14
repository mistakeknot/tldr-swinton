"""Integration tests for semantic search backends.

Covers FAISSBackend build/search cycles, incremental updates, ColBERT
error paths, backend factory selection, sentinel cleanup, and round-trip
serialization of shared types.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tldr_swinton.modules.semantic.backend import (
    BackendInfo,
    BackendStats,
    CodeUnit,
    SearchResult,
    get_backend,
    make_unit_id,
    META_FILENAME,
    _colbert_available,
    _read_index_backend,
)

# ---------------------------------------------------------------------------
# Optional dependency gating
# ---------------------------------------------------------------------------

try:
    import numpy as np
    import faiss

    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

needs_faiss = pytest.mark.skipif(not HAS_FAISS, reason="faiss/numpy not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EMBED_DIM = 16  # small dimension for fast tests


def _make_unit(
    name: str = "foo",
    file: str = "src/mod.py",
    line: int = 10,
    unit_type: str = "function",
    file_hash: str = "aaa111",
) -> CodeUnit:
    """Create a CodeUnit with a deterministic ID."""
    uid = make_unit_id(file, name, line)
    return CodeUnit(
        id=uid,
        name=name,
        file=file,
        line=line,
        unit_type=unit_type,
        signature=f"def {name}():",
        language="python",
        summary=f"Summary for {name}",
        file_hash=file_hash,
    )


class _FakeEmbedder:
    """Deterministic embedder that returns fixed-seed numpy vectors."""

    model = "fake-model"
    model_name = "fake-model"

    def __init__(self, dim: int = EMBED_DIM):
        self._dim = dim
        self._rng = np.random.RandomState(42)

    def is_available(self) -> bool:
        return True

    def embed(self, text: str) -> np.ndarray:
        # Deterministic per-text: seed from text hash for reproducibility
        seed = hash(text) % (2**31)
        rng = np.random.RandomState(seed)
        vec = rng.randn(self._dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed_batch(self, texts: list[str], **kwargs) -> list[np.ndarray]:
        return [self.embed(t) for t in texts]


# ---------------------------------------------------------------------------
# 1. FAISSBackend build/search cycle with mock embedder
# ---------------------------------------------------------------------------


@needs_faiss
class TestFAISSBuildSearchCycle:
    """Full build-then-search roundtrip with mocked embedding."""

    def test_build_and_search_returns_results(self, tmp_path, monkeypatch):
        from tldr_swinton.modules.semantic import faiss_backend as fb_mod

        monkeypatch.setattr(fb_mod, "_get_embedder", lambda *a, **kw: _FakeEmbedder())

        backend = fb_mod.FAISSBackend(str(tmp_path))
        units = [
            _make_unit("alpha", line=1),
            _make_unit("beta", line=20),
            _make_unit("gamma", line=40),
        ]
        texts = ["search for alpha function", "beta does something", "gamma helper"]

        stats = backend.build(units, texts)

        assert stats.total_units == 3
        assert stats.new_units == 3
        assert stats.unchanged_units == 0
        assert stats.backend_name == "faiss"

        results = backend.search("alpha function", k=3)

        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)
        assert all(isinstance(r.unit, CodeUnit) for r in results)
        # All 3 units should be returned (k=3, 3 indexed)
        assert len(results) == 3

    def test_search_returns_correct_metadata(self, tmp_path, monkeypatch):
        from tldr_swinton.modules.semantic import faiss_backend as fb_mod

        monkeypatch.setattr(fb_mod, "_get_embedder", lambda *a, **kw: _FakeEmbedder())

        backend = fb_mod.FAISSBackend(str(tmp_path))
        unit = _make_unit("target_fn", file="src/target.py", line=5)
        backend.build([unit], ["the target function does important work"])

        results = backend.search("target function", k=1)
        assert len(results) == 1
        assert results[0].unit.name == "target_fn"
        assert results[0].unit.file == "src/target.py"
        assert results[0].unit.line == 5
        assert isinstance(results[0].score, float)

    def test_search_empty_index_returns_empty(self, tmp_path, monkeypatch):
        from tldr_swinton.modules.semantic import faiss_backend as fb_mod

        monkeypatch.setattr(fb_mod, "_get_embedder", lambda *a, **kw: _FakeEmbedder())

        backend = fb_mod.FAISSBackend(str(tmp_path))
        results = backend.search("anything", k=5)
        assert results == []


# ---------------------------------------------------------------------------
# 2. FAISSBackend incremental update
# ---------------------------------------------------------------------------


@needs_faiss
class TestFAISSIncrementalUpdate:
    """Incremental update preserves unchanged units and detects changes."""

    def test_incremental_stats(self, tmp_path, monkeypatch):
        from tldr_swinton.modules.semantic import faiss_backend as fb_mod

        monkeypatch.setattr(fb_mod, "_get_embedder", lambda *a, **kw: _FakeEmbedder())

        backend = fb_mod.FAISSBackend(str(tmp_path))

        # First build: 3 units
        u1 = _make_unit("fn_a", file="a.py", line=1, file_hash="hash_a1")
        u2 = _make_unit("fn_b", file="b.py", line=1, file_hash="hash_b1")
        u3 = _make_unit("fn_c", file="c.py", line=1, file_hash="hash_c1")
        stats1 = backend.build(
            [u1, u2, u3],
            ["function a", "function b", "function c"],
        )
        assert stats1.new_units == 3
        assert stats1.unchanged_units == 0

        # Save to disk so next build can load
        backend.save()

        # Second build: fn_b changed (different file_hash), others unchanged
        u1_same = _make_unit("fn_a", file="a.py", line=1, file_hash="hash_a1")
        u2_changed = _make_unit("fn_b", file="b.py", line=1, file_hash="hash_b2")
        u3_same = _make_unit("fn_c", file="c.py", line=1, file_hash="hash_c1")

        # Create a fresh backend to simulate re-indexing
        backend2 = fb_mod.FAISSBackend(str(tmp_path))
        stats2 = backend2.build(
            [u1_same, u2_changed, u3_same],
            ["function a", "function b modified", "function c"],
        )

        assert stats2.total_units == 3
        assert stats2.new_units == 0
        assert stats2.updated_units == 1  # fn_b changed
        assert stats2.unchanged_units == 2  # fn_a, fn_c unchanged


# ---------------------------------------------------------------------------
# 3. ColBERTBackend load error paths
# ---------------------------------------------------------------------------


class TestColBERTLoadErrors:
    """ColBERTBackend.load() should return False for missing/partial indexes."""

    def test_load_returns_false_no_index(self, tmp_path):
        from tldr_swinton.modules.semantic.colbert_backend import ColBERTBackend

        backend = ColBERTBackend(str(tmp_path))
        assert backend.load() is False

    def test_load_returns_false_sentinel_exists(self, tmp_path):
        from tldr_swinton.modules.semantic.colbert_backend import ColBERTBackend

        backend = ColBERTBackend(str(tmp_path))

        # Create the sentinel file indicating a partial build
        sentinel = backend._sentinel_path
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.touch()

        assert backend.load() is False


# ---------------------------------------------------------------------------
# 4. Backend selection via get_backend()
# ---------------------------------------------------------------------------


class TestGetBackend:
    """Factory function get_backend() selects the correct backend."""

    @needs_faiss
    def test_faiss_explicit(self, tmp_path):
        backend = get_backend(str(tmp_path), backend="faiss")
        from tldr_swinton.modules.semantic.faiss_backend import FAISSBackend

        assert isinstance(backend, FAISSBackend)

    def test_colbert_unavailable_raises(self, tmp_path, monkeypatch):
        import tldr_swinton.modules.semantic.backend as backend_mod

        monkeypatch.setattr(backend_mod, "_colbert_available", lambda: False)

        with pytest.raises(RuntimeError, match="pylate"):
            get_backend(str(tmp_path), backend="colbert")

    def test_unknown_backend_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend(str(tmp_path), backend="nonexistent")

    @needs_faiss
    def test_auto_reads_existing_meta(self, tmp_path, monkeypatch):
        import tldr_swinton.modules.semantic.backend as backend_mod

        # Write a meta.json indicating faiss backend
        index_dir = tmp_path / ".tldrs" / "index"
        index_dir.mkdir(parents=True)
        meta = {"backend": "faiss", "version": "1.0"}
        (index_dir / META_FILENAME).write_text(json.dumps(meta))

        # Even if colbert is "available", auto should respect existing meta
        monkeypatch.setattr(backend_mod, "_colbert_available", lambda: True)

        backend = get_backend(str(tmp_path), backend="auto")
        from tldr_swinton.modules.semantic.faiss_backend import FAISSBackend

        assert isinstance(backend, FAISSBackend)

    def test_auto_no_backends_raises(self, tmp_path, monkeypatch):
        import tldr_swinton.modules.semantic.backend as backend_mod

        monkeypatch.setattr(backend_mod, "_colbert_available", lambda: False)
        monkeypatch.setattr(backend_mod, "_faiss_available", lambda: False)

        with pytest.raises(RuntimeError, match="No search backend available"):
            get_backend(str(tmp_path), backend="auto")

    @needs_faiss
    def test_auto_prefers_colbert_when_available(self, tmp_path, monkeypatch):
        """When no existing index and colbert is available, auto should pick colbert."""
        import tldr_swinton.modules.semantic.backend as backend_mod

        monkeypatch.setattr(backend_mod, "_colbert_available", lambda: True)

        # Mock the ColBERTBackend import to avoid actually importing pylate
        mock_colbert_cls = MagicMock()
        mock_colbert_instance = MagicMock()
        mock_colbert_cls.return_value = mock_colbert_instance

        monkeypatch.setattr(
            "tldr_swinton.modules.semantic.colbert_backend.ColBERTBackend",
            mock_colbert_cls,
        )

        backend = get_backend(str(tmp_path), backend="auto")
        mock_colbert_cls.assert_called_once_with(str(tmp_path))


# ---------------------------------------------------------------------------
# 5. Sentinel cleanup
# ---------------------------------------------------------------------------


@needs_faiss
class TestSentinelCleanup:
    """Sentinel files from partial builds should be cleaned up on load."""

    def test_faiss_sentinel_cleaned_on_load(self, tmp_path):
        from tldr_swinton.modules.semantic.faiss_backend import FAISSBackend

        backend = FAISSBackend(str(tmp_path))

        # Create sentinel in the index directory
        sentinel = backend._sentinel_path
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
        assert sentinel.exists()

        # load() should return False AND clean up the sentinel
        result = backend.load()
        assert result is False
        assert not sentinel.exists()

    def test_colbert_sentinel_cleaned_on_load(self, tmp_path):
        from tldr_swinton.modules.semantic.colbert_backend import ColBERTBackend

        backend = ColBERTBackend(str(tmp_path))

        sentinel = backend._sentinel_path
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
        assert sentinel.exists()

        result = backend.load()
        assert result is False
        # ColBERTBackend._cleanup_partial removes sentinel
        assert not sentinel.exists()


# ---------------------------------------------------------------------------
# 6. CodeUnit round-trip serialization
# ---------------------------------------------------------------------------


class TestCodeUnitRoundTrip:
    """CodeUnit.to_dict() -> from_dict() should preserve all fields."""

    def test_round_trip_preserves_fields(self):
        unit = _make_unit(
            name="round_trip_fn",
            file="src/roundtrip.py",
            line=42,
            unit_type="method",
            file_hash="deadbeef",
        )

        data = unit.to_dict()
        restored = CodeUnit.from_dict(data)

        for f in fields(CodeUnit):
            assert getattr(unit, f.name) == getattr(restored, f.name), (
                f"Field {f.name!r} mismatch: {getattr(unit, f.name)!r} != {getattr(restored, f.name)!r}"
            )

    def test_to_dict_returns_plain_dict(self):
        unit = _make_unit()
        data = unit.to_dict()
        assert isinstance(data, dict)
        assert "id" in data
        assert "name" in data
        assert "file" in data
        assert "line" in data
        assert "file_hash" in data

    def test_from_dict_with_extra_keys_raises(self):
        """from_dict with unexpected keys should raise TypeError."""
        unit = _make_unit()
        data = unit.to_dict()
        data["unexpected_field"] = "surprise"
        with pytest.raises(TypeError):
            CodeUnit.from_dict(data)


# ---------------------------------------------------------------------------
# 7. BackendInfo and BackendStats defaults / FAISS info()
# ---------------------------------------------------------------------------


class TestBackendInfoAndStats:
    """BackendInfo and BackendStats have sensible defaults."""

    def test_backend_stats_defaults(self):
        stats = BackendStats()
        assert stats.total_units == 0
        assert stats.new_units == 0
        assert stats.updated_units == 0
        assert stats.unchanged_units == 0
        assert stats.embed_model == ""
        assert stats.backend_name == ""

    def test_backend_info_creation(self):
        info = BackendInfo(
            backend_name="test",
            model="test-model",
            dimension=768,
            count=100,
            index_path="/tmp/test",
        )
        assert info.backend_name == "test"
        assert info.model == "test-model"
        assert info.dimension == 768
        assert info.count == 100
        assert info.extra == {}

    def test_backend_info_extra_field(self):
        info = BackendInfo(
            backend_name="test",
            model="m",
            dimension=1,
            count=0,
            index_path="/tmp",
            extra={"key": "value"},
        )
        assert info.extra == {"key": "value"}

    @needs_faiss
    def test_faiss_info_returns_correct_backend_name(self, tmp_path):
        from tldr_swinton.modules.semantic.faiss_backend import FAISSBackend

        backend = FAISSBackend(str(tmp_path))
        info = backend.info()
        assert info.backend_name == "faiss"
        assert info.count == 0
        assert info.index_path == str(tmp_path / ".tldrs" / "index")

    def test_colbert_info_returns_correct_backend_name(self, tmp_path):
        from tldr_swinton.modules.semantic.colbert_backend import ColBERTBackend

        backend = ColBERTBackend(str(tmp_path))
        info = backend.info()
        assert info.backend_name == "colbert"
        assert info.dimension == 48
        assert info.model == "lightonai/LateOn-Code-edge"
        assert info.count == 0
        assert "pool_factor" in info.extra


# ---------------------------------------------------------------------------
# Helpers: _read_index_backend and make_unit_id
# ---------------------------------------------------------------------------


class TestReadIndexBackend:
    """_read_index_backend reads backend type from meta.json."""

    def test_returns_none_no_index(self, tmp_path):
        assert _read_index_backend(str(tmp_path)) is None

    def test_returns_faiss(self, tmp_path):
        index_dir = tmp_path / ".tldrs" / "index"
        index_dir.mkdir(parents=True)
        (index_dir / META_FILENAME).write_text(json.dumps({"backend": "faiss"}))
        assert _read_index_backend(str(tmp_path)) == "faiss"

    def test_returns_colbert(self, tmp_path):
        index_dir = tmp_path / ".tldrs" / "index"
        index_dir.mkdir(parents=True)
        (index_dir / META_FILENAME).write_text(json.dumps({"backend": "colbert"}))
        assert _read_index_backend(str(tmp_path)) == "colbert"

    def test_returns_none_bad_json(self, tmp_path):
        index_dir = tmp_path / ".tldrs" / "index"
        index_dir.mkdir(parents=True)
        (index_dir / META_FILENAME).write_text("not json")
        assert _read_index_backend(str(tmp_path)) is None


class TestMakeUnitId:
    """make_unit_id produces deterministic, stable IDs."""

    def test_deterministic(self):
        id1 = make_unit_id("file.py", "foo", 10)
        id2 = make_unit_id("file.py", "foo", 10)
        assert id1 == id2

    def test_different_inputs(self):
        id1 = make_unit_id("a.py", "foo", 1)
        id2 = make_unit_id("b.py", "foo", 1)
        assert id1 != id2

    def test_length(self):
        uid = make_unit_id("file.py", "fn", 1)
        assert len(uid) == 16  # sha256[:16]
