#!/usr/bin/env python3
"""
DiffLens Evaluation for tldr-swinton.

Creates a tiny git repo with a diff and measures:
- token savings vs full file
- latency to build diff context
- presence of diff-mapped symbols
"""

from __future__ import annotations

import argparse
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


def _build_fixture_source(dummy_funcs: int = 300, bar_extra: bool = False) -> str:
    lines = [
        "def foo():",
        "    return 1",
        "",
        "def bar():",
        "    value = foo()",
        "    return value + 1" if bar_extra else "    return value",
        "",
    ]
    for idx in range(dummy_funcs):
        lines.append(f"def dummy_{idx:03d}():")
        lines.append(f"    return {idx}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _write_repo(repo: Path) -> None:
    _run_git(repo, ["init"])
    _run_git(repo, ["config", "user.email", "diff-eval@example.com"])
    _run_git(repo, ["config", "user.name", "DiffEval"])

    file_path = repo / "app.py"
    file_path.write_text(_build_fixture_source(dummy_funcs=300, bar_extra=False))
    _run_git(repo, ["add", "app.py"])
    _run_git(repo, ["commit", "-m", "init"])

    file_path.write_text(_build_fixture_source(dummy_funcs=300, bar_extra=True))


def _run_repo_eval(repo: Path, base: str, head: str, label: str) -> EvalResult:
    t0 = time.perf_counter()
    pack = get_diff_context(repo, base=base, head=head, budget_tokens=4000, language="python")
    elapsed = time.perf_counter() - t0

    output = format_context_pack(pack, fmt="ultracompact")
    tokens_pack = count_tokens(output)

    diff_files = _get_diff_files(repo, base, head)
    tokens_full = sum(count_tokens((repo / path).read_text()) for path in diff_files if (repo / path).exists())

    if tokens_full == 0:
        return EvalResult(
            name=f"{label} token savings",
            passed=False,
            details="No diff files found",
        )

    savings = 100.0 * (1.0 - (tokens_pack / max(tokens_full, 1)))

    return EvalResult(
        name=f"{label} token savings",
        passed=True,
        details=f"full={tokens_full}, pack={tokens_pack}, savings={savings:.1f}% (latency={elapsed:.3f}s)",
        metric=savings,
    )


def _get_diff_files(repo: Path, base: str, head: str) -> list[str]:
    def _run(args: list[str]) -> list[str]:
        result = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-only"] + args,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    files = set(_run([f"{base}..{head}"]))
    files.update(_run(["--staged"]))
    files.update(_run([]))
    return sorted(files)


def run_eval() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=None, help="Optional repo path to evaluate")
    parser.add_argument("--base", default=None, help="Base ref for repo eval")
    parser.add_argument("--head", default="HEAD", help="Head ref for repo eval")
    args = parser.parse_args()

    results: list[EvalResult] = []

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

        results.append(EvalResult(
            name="Fixture diff symbol mapped",
            passed=bool(diff_ids),
            details=f"symbols={diff_ids}",
        ))
        results.append(EvalResult(
            name="Fixture token savings vs full file",
            passed=savings >= 0.0,
            details=f"full={tokens_full}, pack={tokens_pack}, savings={savings:.1f}% (latency={elapsed:.3f}s)",
            metric=savings,
        ))

    if args.repo:
        repo_path = Path(args.repo).resolve()
        base = args.base or "HEAD~1"
        results.append(_run_repo_eval(repo_path, base, args.head, label="Repo"))

    print("=" * 70)
    print("DiffLens Evaluation")
    print("=" * 70)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{status}: {r.name}")
        print(f"  {r.details}")

    passed_all = all(r.passed for r in results)
    print("\nSUMMARY:", "PASS" if passed_all else "FAIL")
    return 0 if passed_all else 1


if __name__ == "__main__":
    raise SystemExit(run_eval())
