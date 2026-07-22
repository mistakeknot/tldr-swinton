from __future__ import annotations

from pathlib import Path

from tldr_bench.agent_eval.recon import rank_source_excerpts


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_ranker_prioritizes_public_path_concepts_over_large_generic_files(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/core/change_impact.py",
        "def normalize_module(path):\n    return path\n",
    )
    _write(
        tmp_path,
        "src/core/generic.py",
        ("module analysis package ordinary names impact\n" * 80),
    )

    excerpts = rank_source_excerpts(
        tmp_path,
        "Change-impact analysis reports the wrong package module name.",
    )

    assert excerpts[0].path == "src/core/change_impact.py"


def test_ranker_prioritizes_suspicious_dedup_guard_at_mutation_boundary(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/core/owner.py",
        "class CallGraph:\n"
        "    def add_call(self, caller, callee):\n"
        "        if callee in self.calls[caller]:\n"
        "            self.calls[caller].append(callee)\n",
    )
    _write(
        tmp_path,
        "src/core/consumer.py",
        "def analyze_call_graph(edges):\n"
        "    forward = build_forward_graph(edges)\n"
        "    reverse = build_reverse_graph(edges)\n"
        "    return forward, reverse\n",
    )

    excerpts = rank_source_excerpts(
        tmp_path,
        "Call-graph deduplication dropped forward edges on first insertion when "
        "the same call is observed repeatedly.",
    )

    assert excerpts[0].path == "src/core/owner.py"
