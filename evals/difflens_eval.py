#!/usr/bin/env python3
"""
DiffLens Evaluation for tldr-swinton.

Creates a tiny git repo with a diff and measures:
- token savings vs full file
- latency to build diff context
- presence of diff-mapped symbols
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from tldr_swinton.api import get_diff_context
from tldr_swinton.output_formats import format_context_pack

try:
    import tiktoken

    ENCODER = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(ENCODER.encode(text))
except Exception:

    def count_tokens(text: str) -> int:
        return max(1, len(text) // 4)


@dataclass
class EvalResult:
    name: str
    passed: bool
    details: str
    metric: float = 0.0


def _run_git(repo: Path, args: list[str]) -> None:
    subprocess.run(
        ["git", "-C", str(repo)] + args,
        check=True,
        text=True,
        capture_output=True,
    )


def _write_repo(repo: Path) -> None:
    _run_git(repo, ["init"])
    _run_git(repo, ["config", "user.email", "diff-eval@example.com"])
    _run_git(repo, ["config", "user.name", "DiffEval"])

    file_path = repo / "app.py"
    file_path.write_text(
        "def foo():\n"
        "    return 1\n"
        "\n"
        "def bar():\n"
        "    return foo()\n"
    )
    _run_git(repo, ["add", "app.py"])
    _run_git(repo, ["commit", "-m", "init"])

    file_path.write_text(
        "def foo():\n"
        "    return 1\n"
        "\n"
        "def bar():\n"
        "    value = foo()\n"
        "    return value + 1\n"
    )


def run_eval() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        _write_repo(repo)

        t0 = time.perf_counter()
        pack = get_diff_context(repo, base="HEAD", head="HEAD", budget_tokens=2000, language="python")
        elapsed = time.perf_counter() - t0

        output = format_context_pack(pack, fmt="ultracompact")
        tokens_pack = count_tokens(output)
        tokens_full = count_tokens((repo / "app.py").read_text())
        savings = 100.0 * (1.0 - (tokens_pack / max(tokens_full, 1)))

        diff_ids = [
            item.get("id") for item in pack.get("slices", [])
            if item.get("relevance") == "contains_diff"
        ]

        results = [
            EvalResult(
                name="Diff symbol mapped",
                passed=bool(diff_ids),
                details=f"symbols={diff_ids}",
            ),
            EvalResult(
                name="Token savings vs full file",
                passed=savings >= 0.0,
                details=f"full={tokens_full}, pack={tokens_pack}, savings={savings:.1f}%",
                metric=savings,
            ),
        ]

        print("=" * 70)
        print("DiffLens Evaluation")
        print("=" * 70)
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(f"{status}: {r.name}")
            print(f"  {r.details}")
        print("\nLatency (seconds):")
        print(f"  get_diff_context: {elapsed:.3f}")

        passed_all = all(r.passed for r in results)
        print("\nSUMMARY:", "PASS" if passed_all else "FAIL")
        return 0 if passed_all else 1


if __name__ == "__main__":
    raise SystemExit(run_eval())
