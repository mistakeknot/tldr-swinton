from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tldr_swinton.modules.core.task_context import (
    rank_source_excerpts,
    render_agent_packet,
)


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_ranker_prioritizes_path_concepts_over_large_generic_files(
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
        "module analysis package ordinary names impact\n" * 80,
    )

    excerpts = rank_source_excerpts(
        tmp_path,
        "Change-impact analysis reports the wrong package module name.",
    )

    assert excerpts[0].path == "src/core/change_impact.py"


def test_ranker_prioritizes_a_suspicious_dedup_guard(tmp_path: Path) -> None:
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


def test_agent_packet_includes_bounded_context_and_execution_contract(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "src/owner.py", "def normalize_widget(widget):\n    return widget\n")

    packet = render_agent_packet(
        tmp_path,
        "Fix widget normalization",
        test_command="uv run pytest tests/test_owner.py",
        max_files=1,
        max_chars=120,
    )

    assert "Use the precomputed candidates below to bound the first source read" in packet
    assert "Defer task trackers, Git history and remotes" in packet
    assert "Validated execution contract" in packet
    assert "`uv run pytest tests/test_owner.py`" in packet
    assert "src/owner.py:1" in packet


def test_test_command_routes_matching_source_owner_before_test_facade(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/pkg/url_safe.py",
        "def decode_url_safe_base64(value):\n    return value\n",
    )
    _write(
        tmp_path,
        "src/pkg/encoding.py",
        "def decode_base64(value):\n    return value\n",
    )
    _write(
        tmp_path,
        "tests/pkg/test_encoding.py",
        "def test_decode_base64():\n    assert True\n",
    )

    packet = render_agent_packet(
        tmp_path,
        "URL-safe base64 decoding fails for unpadded values.",
        test_command="python -m pytest tests/pkg/test_encoding.py -q",
        max_files=3,
        max_chars=1_500,
    )

    assert packet.index("Candidate 1: src/pkg/encoding.py") < packet.index(
        "src/pkg/url_safe.py"
    )


def test_packet_cli_emits_machine_readable_ranked_excerpts(tmp_path: Path) -> None:
    _write(tmp_path, "src/owner.py", "def normalize_widget(widget):\n    return widget\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "--machine",
            "packet",
            "Fix widget normalization",
            "--project",
            str(tmp_path),
            "--max-files",
            "1",
            "--max-chars",
            "120",
            "--test-command",
            "uv run pytest tests/test_owner.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["result"]["excerpts"][0]["path"] == "src/owner.py"
    assert payload["result"]["test_command"] == "uv run pytest tests/test_owner.py"
