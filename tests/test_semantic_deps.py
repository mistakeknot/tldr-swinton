import builtins

import pytest

import tldr_swinton.modules.semantic.faiss_backend as fb_mod


def test_require_numpy_missing(monkeypatch) -> None:
    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "numpy":
            raise ImportError("no numpy")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError) as exc:
        fb_mod._require_numpy()

    assert "semantic-ollama" in str(exc.value)


def test_require_faiss_missing(monkeypatch) -> None:
    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faiss":
            raise ImportError("no faiss")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError) as exc:
        fb_mod._require_faiss()

    assert "semantic-ollama" in str(exc.value)
