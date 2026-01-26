"""OpenHands benchmark runner with success rate tracking.

This runner executes tasks using the OpenHands harness and tracks
success rates for correlation analysis with token savings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import subprocess
import time

from tldr_bench.openhands import resolve_bench_dir
from tldr_bench.success_correlation import TaskOutcome, SuccessCorrelator


def _parse_swe_bench_results(output_dir: Path) -> dict[str, dict[str, Any]]:
    """Parse SWE-bench evaluation results from output directory."""
    results = {}

    # Look for evaluation result files
    for pattern in ["*.json", "**/*.json"]:
        for result_file in output_dir.glob(pattern):
            if "eval" in result_file.name.lower() or "result" in result_file.name.lower():
                try:
                    with open(result_file) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if "instance_id" in item:
                                results[item["instance_id"]] = item
                    elif isinstance(data, dict) and "instance_id" in data:
                        results[data["instance_id"]] = data
                except (json.JSONDecodeError, OSError):
                    continue

    return results


def run_task(task: dict[str, Any], variant: str) -> dict[str, Any]:
    """Run a single task using the OpenHands harness.

    Args:
        task: Task configuration with id, benchmark, llm_config, etc.
        variant: Variant identifier (e.g., 'baseline', 'tldrs-context')

    Returns:
        Result dict with task_id, variant_id, status, and execution details.
    """
    task_id = task.get("id")
    if not task_id:
        raise ValueError("task.id is required")
    if not variant:
        raise ValueError("variant is required")

    start_time = time.perf_counter()

    # Handle direct bench_command execution
    bench_command = task.get("bench_command")
    if bench_command:
        result = subprocess.run(
            bench_command,
            text=True,
            capture_output=True,
            check=False,
        )
        execution_time = int((time.perf_counter() - start_time) * 1000)
        status = "completed" if result.returncode == 0 else "failed"
        return {
            "task_id": task_id,
            "variant_id": variant,
            "status": status,
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "execution_time_ms": execution_time,
        }

    # Resolve OpenHands bench directory
    try:
        bench_dir = resolve_bench_dir()
    except FileNotFoundError:
        bench_dir = None

    llm_config = task.get("llm_config") or os.getenv("OH_LLM_CONFIG")
    benchmark = task.get("benchmark")

    if bench_dir and llm_config and benchmark:
        # Build inference command
        command = ["uv", "run", f"{benchmark}-infer", llm_config]

        select = task.get("select")
        if select:
            command.extend(["--select", select])
        max_iterations = task.get("max_iterations")
        if max_iterations:
            command.extend(["--max-iterations", str(max_iterations)])
        num_workers = task.get("num_workers")
        if num_workers:
            command.extend(["--num-workers", str(num_workers)])
        max_retries = task.get("max_retries")
        if max_retries is not None:
            command.extend(["--max-retries", str(max_retries)])

        # Add TLDRS context injection for tldrs variants
        env = os.environ.copy()
        if "tldrs" in variant.lower():
            env["TLDRS_ENABLED"] = "1"
            env["TLDRS_VARIANT"] = variant

        result = subprocess.run(
            command,
            cwd=bench_dir,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

        execution_time = int((time.perf_counter() - start_time) * 1000)
        status = "completed" if result.returncode == 0 else "failed"

        return {
            "task_id": task_id,
            "variant_id": variant,
            "status": status,
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "bench_dir": str(bench_dir),
            "command": command,
            "execution_time_ms": execution_time,
        }

    return {
        "task_id": task_id,
        "variant_id": variant,
        "status": "not_implemented",
        "success": False,
        "bench_dir": str(bench_dir) if bench_dir else None,
        "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
    }


def run_task_with_tracking(
    task: dict[str, Any],
    variant: str,
    baseline_tokens: int | None = None,
) -> TaskOutcome:
    """Run task and return TaskOutcome for correlation analysis.

    Args:
        task: Task configuration
        variant: Variant identifier
        baseline_tokens: Token count for baseline comparison

    Returns:
        TaskOutcome suitable for SuccessCorrelator
    """
    result = run_task(task, variant)

    # Extract token usage from result or estimate
    tokens_used = result.get("tokens_used", 0)
    if not tokens_used and result.get("stdout"):
        # Try to parse token count from output
        import re

        match = re.search(r"tokens?[:\s]+(\d+)", result.get("stdout", ""), re.IGNORECASE)
        if match:
            tokens_used = int(match.group(1))

    return TaskOutcome(
        task_id=result["task_id"],
        variant=result["variant_id"],
        success=result.get("success", False),
        tokens_used=tokens_used,
        baseline_tokens=baseline_tokens,
        execution_time_ms=result.get("execution_time_ms"),
        error_category=result.get("error_category"),
    )


def run_swe_bench_subset(
    instances: list[str],
    variants: list[str],
    output_dir: Path,
    llm_config: str | None = None,
) -> SuccessCorrelator:
    """Run SWE-bench subset with multiple variants and track success rates.

    Args:
        instances: List of SWE-bench instance IDs to run
        variants: List of variant names (e.g., ['baseline', 'tldrs-context'])
        output_dir: Directory for output files
        llm_config: LLM config path (or uses OH_LLM_CONFIG env)

    Returns:
        SuccessCorrelator with all recorded outcomes
    """
    correlator = SuccessCorrelator()
    output_dir.mkdir(parents=True, exist_ok=True)

    for instance_id in instances:
        baseline_tokens: int | None = None

        for variant in variants:
            task = {
                "id": instance_id,
                "benchmark": "swe-bench",
                "llm_config": llm_config,
                "select": instance_id,
            }

            outcome = run_task_with_tracking(task, variant, baseline_tokens)
            correlator.record(outcome)

            # Capture baseline tokens for subsequent comparisons
            if variant == "baseline" or (baseline_tokens is None and variant == variants[0]):
                baseline_tokens = outcome.tokens_used

    # Save outcomes to file
    correlator.save_to_file(output_dir / "outcomes.jsonl")

    # Generate and save report
    report = correlator.compute_correlation()
    with open(output_dir / "correlation_report.json", "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    # Write human-readable summary
    with open(output_dir / "correlation_summary.txt", "w") as f:
        f.write(report.summary())

    return correlator
