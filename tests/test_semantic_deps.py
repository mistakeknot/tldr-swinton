import builtins

import pytest

import tldr_swinton.index as index_mod


def test_require_semantic_deps_missing_numpy(monkeypatch) -> None:
    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "numpy":
            raise ImportError("no numpy")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError) as exc:
        index_mod._require_semantic_deps()

    assert "semantic-ollama" in str(exc.value)


def test_require_semantic_deps_missing_faiss(monkeypatch) -> None:
    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faiss":
            raise ImportError("no faiss")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError) as exc:
        index_mod._require_semantic_deps()

    assert "semantic-ollama" in str(exc.value)
