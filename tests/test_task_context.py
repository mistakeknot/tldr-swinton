from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tldr_swinton.modules.core.task_context import (
    build_agent_packet,
    rank_source_excerpts,
    recommended_packet_max_chars,
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


def test_ranker_includes_shell_owners_and_ignores_worktree_copies(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/dispatch.sh",
        "build_backend_command() {\n"
        "    context_gateway_prepare \"$prompt\" \"$workdir\"\n"
        "}\n",
    )
    _write(
        tmp_path,
        ".worktrees/stale/scripts/dispatch.sh",
        "build_backend_command() {\n"
        "    legacy_context_gateway_prepare \"$prompt\" \"$workdir\"\n"
        "}\n",
    )
    _write(
        tmp_path,
        "tests/structural/test_dispatch.py",
        "def test_dispatch_context_gateway():\n    assert True\n",
    )

    excerpts = rank_source_excerpts(
        tmp_path,
        "Modify scripts/dispatch.sh so the context gateway prepares the prompt "
        "before building the backend command.",
    )

    assert excerpts[0].path == "scripts/dispatch.sh"
    assert all(".worktrees" not in excerpt.path for excerpt in excerpts)


def test_ranker_includes_bats_contracts(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/shell/dispatch_context_gateway.bats",
        '@test "dispatch injects context gateway packet" {\n'
        '  run dispatch --context-gateway auto "fix owner"\n'
        '  [ "$status" -eq 0 ]\n'
        "}\n",
    )
    _write(
        tmp_path,
        "src/generic.py",
        "def dispatch(value):\n    return value\n",
    )

    excerpts = rank_source_excerpts(
        tmp_path,
        "Update the Bats dispatch context gateway contract.",
    )

    assert excerpts[0].path == "tests/shell/dispatch_context_gateway.bats"


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


def test_recommended_budget_is_model_and_owner_signal_aware() -> None:
    test_command = "python -m pytest tests/pkg/test_encoding.py -q"

    assert recommended_packet_max_chars("generic", test_command) == 1_500
    assert recommended_packet_max_chars("claude", test_command) == 1_500
    assert recommended_packet_max_chars("kimi", test_command) == 1_500
    assert recommended_packet_max_chars("codex", test_command) == 750
    assert recommended_packet_max_chars("codex", "go test ./cmp/cmpopts") == 1_500


def test_packet_assessment_trusts_an_explicit_owner_path(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/dispatch.sh",
        "context_gateway_prepare() {\n    printf '%s' \"$prompt\"\n}\n",
    )
    _write(
        tmp_path,
        "tests/test_dispatch.py",
        "def test_context_gateway_prepare():\n    assert True\n",
    )

    result = build_agent_packet(
        tmp_path,
        "Modify scripts/dispatch.sh so context_gateway_prepare injects the packet.",
        harness_profile="codex",
    )

    assert result.decision == "inject"
    assert result.reason == "explicit_path"
    assert result.confidence == 1.0
    assert result.excerpts[0].path == "scripts/dispatch.sh"


def test_packet_assessment_falls_back_when_ranked_owners_are_tied(
    tmp_path: Path,
) -> None:
    source = "def normalize_widget(widget):\n    return widget\n"
    _write(tmp_path, "src/a/widget.py", source)
    _write(tmp_path, "src/b/widget.py", source)

    result = build_agent_packet(tmp_path, "Fix widget normalization")

    assert result.decision == "fallback"
    assert result.reason == "low_confidence"
    assert result.confidence < 0.6
    assert result.packet == ""
    assert {excerpt.path for excerpt in result.excerpts} == {
        "src/a/widget.py",
        "src/b/widget.py",
    }


def test_packet_assessment_falls_back_without_source_candidates(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "widget normalization\n")

    result = build_agent_packet(tmp_path, "Fix widget normalization")

    assert result.decision == "fallback"
    assert result.reason == "no_candidates"
    assert result.confidence == 0.0
    assert result.packet == ""


def test_packet_receipt_hashes_the_exact_packet_without_prompt_text(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/owner.py",
        "def normalize_widget(widget):\n    return widget\n",
    )
    secret_marker = "customer-ticket-49382"

    result = build_agent_packet(
        tmp_path,
        f"Fix widget normalization for {secret_marker}",
    )
    payload = result.as_dict()
    receipt = payload["receipt"]

    assert result.decision == "inject"
    assert receipt["schema_version"] == 1
    assert receipt["decision"] == "inject"
    assert receipt["packet_chars"] == len(result.packet)
    assert receipt["packet_sha256"] == hashlib.sha256(
        result.packet.encode()
    ).hexdigest()
    assert receipt["candidate_paths"] == ["src/owner.py"]
    assert secret_marker not in json.dumps(receipt)


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
    packet_result = payload["result"]
    assert packet_result["schema_version"] == 1
    assert packet_result["decision"] == "inject"
    assert packet_result["packet"].startswith("# Agent context packet")
    assert packet_result["receipt"]["decision"] == "inject"
    assert packet_result["excerpts"][0]["path"] == "src/owner.py"
    assert packet_result["test_command"] == "uv run pytest tests/test_owner.py"


def test_packet_cli_applies_codex_owner_hint_budget(tmp_path: Path) -> None:
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
            "--harness-profile",
            "codex",
            "--test-command",
            "python -m pytest tests/test_owner.py -q",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)["result"]
    assert payload["harness_profile"] == "codex"
    assert payload["max_chars"] == 750


def test_packet_cli_accepts_kimi_profile_and_confidence_override(
    tmp_path: Path,
) -> None:
    source = "def normalize_widget(widget):\n    return widget\n"
    _write(tmp_path, "src/a/widget.py", source)
    _write(tmp_path, "src/b/widget.py", source)

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
            "--harness-profile",
            "kimi",
            "--min-confidence",
            "0.5",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)["result"]
    assert payload["harness_profile"] == "kimi"
    assert payload["max_chars"] == 1_500
    assert payload["decision"] == "inject"
