from pathlib import Path

from tldr_swinton import api


def test_adjacency_dedupes_and_sorts_calls(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "b.py").write_text("def bar():\n    return 2\n")
    (tmp_path / "c.py").write_text("def baz():\n    return 3\n")

    class DummyGraph:
        edges = [
            (str(tmp_path / "a.py"), "foo", str(tmp_path / "c.py"), "baz"),
            (str(tmp_path / "a.py"), "foo", str(tmp_path / "b.py"), "bar"),
            (str(tmp_path / "a.py"), "foo", str(tmp_path / "b.py"), "bar"),
        ]

    monkeypatch.setattr(api, "build_project_call_graph", lambda *args, **kwargs: DummyGraph())

    ctx = api.get_relevant_context(tmp_path, "foo", depth=1)
    foo_ctx = next(func for func in ctx.functions if func.name.endswith(":foo"))
    assert foo_ctx.calls == ["b.py:bar", "c.py:baz"]
