from pathlib import Path

import pytest

from tldr_swinton.cross_file_calls import build_project_call_graph
from tldr_swinton.hybrid_extractor import TREE_SITTER_AVAILABLE


@pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter-typescript not available")
def test_typescript_this_method_is_class_qualified(tmp_path: Path) -> None:
    (tmp_path / "mod.ts").write_text(
        """
class A {
  helper(): number { return 1; }
  run(): number { return this.helper(); }
}
""".lstrip()
    )

    graph = build_project_call_graph(str(tmp_path), language="typescript")
    edge_names = {edge[1] for edge in graph.edges} | {edge[3] for edge in graph.edges}

    assert "A.run" in edge_names
    assert "A.helper" in edge_names
