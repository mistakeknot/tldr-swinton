#!/usr/bin/env python3
"""
DiffLens Evaluation for tldr-swinton.

Creates a tiny git repo with a diff and measures:
- token savings vs full file
- latency to build diff context
- presence of diff-mapped symbols
- range-encoded diff_lines and windowed code (when applicable)
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


def _build_module_source(
    module_prefix: str,
    class_name: str,
    helper_extra: bool,
    method_extra: bool,
    method_count: int = 8,
    func_count: int = 55,
) -> str:
    lines: list[str] = [
        "from __future__ import annotations",
        "",
        f"class {class_name}:",
        "    def __init__(self, seed: int):",
        "        self.seed = seed",
        "",
    ]

    method_suffix = " + 1" if method_extra else ""
    for idx in range(method_count):
        lines.append(f"    def method_{idx}(self, value: int) -> int:")
        lines.append(f"        base = value + {idx}")
        lines.append(f"        return base + self.seed{method_suffix}")
        lines.append("")

    helper_suffix = " + 2" if helper_extra else " + 1"
    lines.extend(
        [
            f"def {module_prefix}_helper(value: int) -> int:",
            f"    return value{helper_suffix}",
            "",
            f"def {module_prefix}_pipeline(value: int) -> int:",
            f"    obj = {class_name}(value)",
            f"    return {module_prefix}_helper(obj.method_0(value))",
            "",
        ]
    )

    for idx in range(func_count):
        lines.append(f"def {module_prefix}_{idx:02d}(value: int) -> int:")
        lines.append(f"    temp = {module_prefix}_helper(value)")
        lines.append(f"    return temp + {idx}")
        lines.append("")

    return "\n".join(lines) + "\n"


def _build_multifile_fixture_sources(
    changed_modules: set[str] | None = None,
) -> dict[str, str]:
    groups = ("core", "models", "services", "utils", "handlers")
    sources: dict[str, str] = {}
    changed_modules = changed_modules or set()

    for group in groups:
        for idx in range(5):
            module_name = f"{group}_{idx}"
            class_name = f"{group.title()}{idx}"
            helper_extra = module_name in changed_modules
            method_extra = module_name in changed_modules
            sources[f"{module_name}.py"] = _build_module_source(
                module_prefix=module_name,
                class_name=class_name,
                helper_extra=helper_extra,
                method_extra=method_extra,
            )

    return sources


def _build_ts_module_source(
    module_prefix: str,
    class_name: str,
    helper_extra: bool,
    method_extra: bool,
    method_count: int = 6,
    func_count: int = 35,
) -> str:
    lines: list[str] = [
        "export type Payload = { value: number };",
        "",
        f"export class {class_name} {{",
        "  private seed: number;",
        "  constructor(seed: number) {",
        "    this.seed = seed;",
        "  }",
        "",
    ]

    method_suffix = " + 1" if method_extra else ""
    for idx in range(method_count):
        lines.append(f"  method{idx}(value: number): number {{")
        lines.append(f"    const base = value + {idx};")
        lines.append(f"    return base + this.seed{method_suffix};")
        lines.append("  }")
        lines.append("")

    helper_suffix = " + 2" if helper_extra else " + 1"
    lines.extend(
        [
            "}",
            "",
            f"export function {module_prefix}Helper(value: number): number {{",
            f"  return value{helper_suffix};",
            "}",
            "",
            f"export function {module_prefix}Pipeline(payload: Payload): number {{",
            f"  const obj = new {class_name}(payload.value);",
            f"  return {module_prefix}Helper(obj.method0(payload.value));",
            "}",
            "",
        ]
    )

    for idx in range(func_count):
        lines.append(f"export function {module_prefix}Fn{idx}(value: number): number {{")
        lines.append(f"  const temp = {module_prefix}Helper(value);")
        lines.append(f"  return temp + {idx};")
        lines.append("}")
        lines.append("")

    return "\n".join(lines) + "\n"


def _build_ts_fixture_sources(
    changed_modules: set[str] | None = None,
) -> dict[str, str]:
    groups = ("core", "models", "services", "utils")
    sources: dict[str, str] = {}
    changed_modules = changed_modules or set()

    for group in groups:
        for idx in range(3):
            module_name = f"{group}{idx}"
            class_name = f"{group.title()}{idx}"
            helper_extra = module_name in changed_modules
            method_extra = module_name in changed_modules
            sources[f"{module_name}.ts"] = _build_ts_module_source(
                module_prefix=module_name,
                class_name=class_name,
                helper_extra=helper_extra,
                method_extra=method_extra,
            )

    return sources


def _build_window_fixture_source() -> str:
    lines = ["def foo():"]
    for idx in range(1, 45):
        lines.append(f"    line{idx} = {idx}")
    lines.append("    return line44")
    return "\n".join(lines) + "\n"


def _write_multifile_repo(repo: Path) -> None:
    _run_git(repo, ["init"])
    _run_git(repo, ["config", "user.email", "diff-eval@example.com"])
    _run_git(repo, ["config", "user.name", "DiffEval"])

    sources = _build_multifile_fixture_sources()
    for name, source in sources.items():
        (repo / name).write_text(source)

    _run_git(repo, ["add", "."])
    _run_git(repo, ["commit", "-m", "init"])

    updated = _build_multifile_fixture_sources({"core_0", "utils_0"})
    for name, source in updated.items():
        if sources.get(name) != source:
            (repo / name).write_text(source)


def _write_ts_repo(repo: Path) -> None:
    _run_git(repo, ["init"])
    _run_git(repo, ["config", "user.email", "diff-eval@example.com"])
    _run_git(repo, ["config", "user.name", "DiffEval"])

    sources = _build_ts_fixture_sources()
    for name, source in sources.items():
        (repo / name).write_text(source)

    _run_git(repo, ["add", "."])
    _run_git(repo, ["commit", "-m", "init"])

    updated = _build_ts_fixture_sources({"core0", "utils0"})
    for name, source in updated.items():
        if sources.get(name) != source:
            (repo / name).write_text(source)


def _write_window_repo(repo: Path) -> None:
    _run_git(repo, ["init"])
    _run_git(repo, ["config", "user.email", "diff-eval@example.com"])
    _run_git(repo, ["config", "user.name", "DiffEval"])

    file_path = repo / "app.py"
    file_path.write_text(_build_window_fixture_source())
    _run_git(repo, ["add", "app.py"])
    _run_git(repo, ["commit", "-m", "init"])

    lines = _build_window_fixture_source().splitlines()
    lines[2] = "    line2 = 999"
    lines[29] = "    line29 = 999"
    file_path.write_text("\n".join(lines) + "\n")


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


def _run_fixture_eval(repo: Path, language: str, label: str) -> list[EvalResult]:
    t0 = time.perf_counter()
    pack = get_diff_context(repo, base="HEAD", head="HEAD", budget_tokens=2000, language=language)
    elapsed = time.perf_counter() - t0

    output = format_context_pack(pack, fmt="ultracompact")
    tokens_pack = count_tokens(output)
    diff_files = _get_diff_files(repo, "HEAD", "HEAD")
    tokens_full = sum(
        count_tokens((repo / path).read_text())
        for path in diff_files
        if (repo / path).exists()
    )
    savings = 100.0 * (1.0 - (tokens_pack / max(tokens_full, 1)))

    diff_ids = [
        item.get("id") for item in pack.get("slices", [])
        if item.get("relevance") == "contains_diff"
    ]

    return [
        EvalResult(
            name=f"{label} diff symbol mapped",
            passed=bool(diff_ids),
            details=f"symbols={diff_ids}",
        ),
        EvalResult(
            name=f"{label} token savings vs full files",
            passed=savings >= 0.0,
            details=f"full={tokens_full}, pack={tokens_pack}, savings={savings:.1f}% (latency={elapsed:.3f}s)",
            metric=savings,
        ),
    ]


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
        _write_multifile_repo(repo)
        results.extend(_run_fixture_eval(repo, language="python", label="Fixture (Python)"))

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        _write_ts_repo(repo)
        results.extend(_run_fixture_eval(repo, language="typescript", label="Fixture (TypeScript)"))

    with tempfile.TemporaryDirectory() as tmpdir:
        window_repo = Path(tmpdir)
        _write_window_repo(window_repo)
        pack = get_diff_context(window_repo, base="HEAD", head="HEAD", budget_tokens=2000, language="python")
        slices = pack.get("slices", [])
        diff_lines = slices[0].get("diff_lines") if slices else None
        code = slices[0].get("code") if slices else None

        ranges_ok = isinstance(diff_lines, list) and all(
            isinstance(item, list) and len(item) == 2 for item in diff_lines or []
        )
        code_windowed = bool(code and "..." in code)

        results.append(EvalResult(
            name="Diff lines are range-encoded",
            passed=ranges_ok,
            details=f"diff_lines={diff_lines}",
        ))
        results.append(EvalResult(
            name="Windowed diff code contains separators",
            passed=code_windowed,
            details="windowed" if code_windowed else "full",
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
