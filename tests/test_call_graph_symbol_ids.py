from pathlib import Path

from tldr_swinton.analysis import impact_analysis
from tldr_swinton.cross_file_calls import build_project_call_graph


def test_call_graph_uses_qualified_method_names(tmp_path: Path) -> None:
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "mod.py").write_text(
        """
class A:
    def run(self):
        helper()

class B:
    def run(self):
        helper()

def helper():
    return 1

def call():
    A.run()
""".lstrip()
    )

    graph = build_project_call_graph(str(tmp_path), language="python")
    # Ensure both qualified method names appear in graph edges
    edge_names = {edge[1] for edge in graph.edges} | {edge[3] for edge in graph.edges}
    assert "A.run" in edge_names
    assert "B.run" in edge_names

    result = impact_analysis(graph, "A.run", target_file="pkg/mod.py")
    assert "pkg/mod.py:A.run" in result["targets"]
