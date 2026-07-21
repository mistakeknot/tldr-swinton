from __future__ import annotations

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core.ast_extractor import CallGraphInfo  # noqa: E402


def forward_edge() -> None:
    graph = CallGraphInfo()
    graph.add_call("caller", "callee")
    assert graph.calls == {"caller": ["callee"]}


def repeated_edge() -> None:
    graph = CallGraphInfo()
    graph.add_call("caller", "callee")
    graph.add_call("caller", "callee")
    assert graph.calls == {"caller": ["callee"]}
    assert graph.called_by == {"callee": ["caller"]}


run([("forward edge", forward_edge), ("deduplicated edge", repeated_edge)])
