#!/usr/bin/env python3
"""
VHS Output Evaluation for tldr-swinton + tldrs-vhs.

Measures:
- Token savings for vhs:// ref vs inline output
- Latency for vhs put/get
- Round-trip integrity
- CLI integration: tldrs context --output vhs + --include vhs://...

This eval is optional and will SKIP if tldrs-vhs is not available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


def _run(cmd: list[str], input_text: Optional[str] = None, env: Optional[dict] = None) -> tuple[str, str, int, float]:
    t0 = time.perf_counter()
    result = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
    )
    dt = time.perf_counter() - t0
    return result.stdout, result.stderr, result.returncode, dt


def _find_vhs_runner(repo_root: Path) -> tuple[list[str], dict] | None:
    # Prefer explicit override
    override = os.environ.get("TLDRS_VHS_CMD")
    if override:
        return override.split(), None

    if shutil.which("tldrs-vhs"):
        return ["tldrs-vhs"], None

    # Optional: run via python -m with PYTHONPATH
    vhs_src = os.environ.get("TLDRS_VHS_PYTHONPATH")
    if vhs_src:
        env = {**os.environ, "PYTHONPATH": vhs_src}
        return [sys.executable, "-m", "tldrs_vhs.cli"], env

    # Developer fallback: sibling repo at ../tldrs-vhs/src
    sibling = repo_root.parent / "tldrs-vhs" / "src"
    if sibling.exists():
        env = {**os.environ, "PYTHONPATH": str(sibling)}
        return [sys.executable, "-m", "tldrs_vhs.cli"], env

    return None


def run_eval() -> int:
    repo = Path(__file__).resolve().parents[1]

    vhs_runner = _find_vhs_runner(repo)
    if vhs_runner is None:
        print("SKIP: tldrs-vhs not found. Set TLDRS_VHS_CMD or TLDRS_VHS_PYTHONPATH.")
        return 0

    vhs_cmd, vhs_env = vhs_runner
    vhs_env = vhs_env or os.environ.copy()

    tldrs_env = os.environ.copy()
    if vhs_cmd and vhs_cmd[0] == sys.executable:
        tldrs_env["TLDRS_VHS_CMD"] = f"{sys.executable} -m tldrs_vhs.cli"
        if "PYTHONPATH" in vhs_env:
            tldrs_env["TLDRS_VHS_PYTHONPATH"] = vhs_env["PYTHONPATH"]

    # 1) Get context output (inline)
    ctx_cmd = [
        "tldrs",
        "context",
        "src/tldr_swinton/api.py:get_relevant_context",
        "--project",
        str(repo),
        "--depth",
        "1",
        "--format",
        "text",
    ]
    ctx_out, ctx_err, code, ctx_time = _run(ctx_cmd, env=tldrs_env)
    if code != 0:
        print(ctx_err)
        return 1

    ctx_tokens = count_tokens(ctx_out)

    # 2) Put into VHS
    put_out, put_err, code, put_time = _run(vhs_cmd + ["put", "-"], input_text=ctx_out, env=vhs_env)
    if code != 0:
        print(put_err)
        return 1
    ref = put_out.strip().splitlines()[-1]
    ref_tokens = count_tokens(ref)

    # 3) Get back and verify
    get_out, get_err, code, get_time = _run(vhs_cmd + ["get", ref], env=vhs_env)
    if code != 0:
        print(get_err)
        return 1
    round_trip_ok = get_out == ctx_out

    # 4) tldrs context --output vhs
    ctx_vhs_out, ctx_vhs_err, code, ctx_vhs_time = _run(ctx_cmd + ["--output", "vhs"], env=tldrs_env)
    if code != 0:
        print(ctx_vhs_err)
        return 1
    ctx_vhs_ref = ctx_vhs_out.strip().splitlines()[-1]

    # 5) tldrs context --include vhs://
    include_out, include_err, code, include_time = _run(ctx_cmd + ["--include", ctx_vhs_ref], env=tldrs_env)
    if code != 0:
        print(include_err)
        return 1
    include_ok = f"Included {ctx_vhs_ref}" in include_out

    # Results
    results: list[EvalResult] = []

    savings = 100.0 * (1.0 - (ref_tokens / max(ctx_tokens, 1)))
    results.append(EvalResult(
        name="VHS ref token savings",
        passed=savings >= 90.0,
        details=f"Context tokens: {ctx_tokens}, ref tokens: {ref_tokens}, savings: {savings:.1f}%",
        metric=savings,
    ))

    results.append(EvalResult(
        name="VHS round-trip integrity",
        passed=round_trip_ok,
        details=f"Round-trip ok: {round_trip_ok}",
    ))

    results.append(EvalResult(
        name="tldrs context --output vhs",
        passed=ctx_vhs_ref.startswith("vhs://"),
        details=f"Ref: {ctx_vhs_ref}",
    ))

    results.append(EvalResult(
        name="tldrs context --include vhs",
        passed=include_ok,
        details="Include marker found" if include_ok else "Include marker missing",
    ))

    print("=" * 70)
    print("tldrs-vhs Evaluation")
    print("=" * 70)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{status}: {r.name}")
        print(f"  {r.details}")
    print("\nLatency (seconds):")
    print(f"  context: {ctx_time:.3f}")
    print(f"  vhs put: {put_time:.3f}")
    print(f"  vhs get: {get_time:.3f}")
    print(f"  context --output vhs: {ctx_vhs_time:.3f}")
    print(f"  context --include: {include_time:.3f}")

    passed_all = all(r.passed for r in results)
    print("\nSUMMARY:", "PASS" if passed_all else "FAIL")
    return 0 if passed_all else 1


if __name__ == "__main__":
    raise SystemExit(run_eval())
