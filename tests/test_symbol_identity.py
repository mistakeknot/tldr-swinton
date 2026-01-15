from pathlib import Path

from tldr_swinton.analysis import impact_analysis
from tldr_swinton.cross_file_calls import build_project_call_graph
from tldr_swinton.engines.symbolkite import get_relevant_context


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_symbol_identity_is_file_qualified(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "def dup():\n    return 1\n")
    _write(tmp_path / "b.py", "def dup():\n    return 2\n")
    _write(
        tmp_path / "c.py",
        "from a import dup\n\n"
        "def caller():\n"
        "    return dup()\n",
    )

    graph = build_project_call_graph(str(tmp_path), language="python")
    result = impact_analysis(graph, "dup", target_file="a.py")

    assert "error" not in result
    assert any("a.py:dup" in key for key in result["targets"].keys())

    ctx = get_relevant_context(tmp_path, "a.py:dup", depth=1, language="python")
    names = [func.name for func in ctx.functions]
    assert any(name.endswith("a.py:dup") for name in names)
    assert all("b.py:dup" not in name for name in names)
