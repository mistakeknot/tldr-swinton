from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import EvaluationAnalysis, RoutingGate, analyze_outcomes
from .codex_runner import CodexRunConfig, build_codex_command, run_codex
from .policy import AdaptivePolicy
from .report import write_reports
from .schema import Condition, RunOutcome, TaskCategory, TaskSpec
from .tasks import load_agent_tasks
from .workspace import (
    build_condition_environment,
    capture_patch,
    changed_paths,
    load_replacements,
    materialize_workspace,
    patch_hash,
    run_external_grader,
)


REPO_ROOT = Path(__file__).parents[3]
DEFAULT_TASKS_FILE = Path(__file__).parents[1] / "tasks" / "agent_value.yaml"
SMOKE_TASK_IDS = ("neg-token-fallback", "cross-gitignore-nested")
FORMAT_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the paired end-to-end tldrs agent value evaluation."
    )
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--task", action="append", default=[])
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=[condition.value for condition in Condition],
        default=[condition.value for condition in Condition],
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--model", default=os.environ.get("TLDRS_EVAL_MODEL", "gpt-5.6-sol")
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="medium",
    )
    parser.add_argument(
        "--adaptive-policy",
        choices=[policy.value for policy in AdaptivePolicy],
        default=AdaptivePolicy.CURRENT.value,
        help="routing guidance used by the adaptive condition",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-workspaces", action="store_true")
    parser.add_argument("--codex-executable", type=Path, default=Path("codex"))
    parser.add_argument(
        "--grader-python", type=Path, default=Path(sys.executable)
    )
    parser.add_argument(
        "--tldrs-bin-dir", type=Path, default=Path("/Users/sma/.local/bin")
    )
    parser.add_argument("--tasks-file", type=Path, default=DEFAULT_TASKS_FILE)
    parser.add_argument(
        "--source-repo",
        type=Path,
        default=REPO_ROOT,
        help="clean Git checkout whose HEAD is materialized for every cell",
    )
    return parser


def _default_results_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "tldr-bench/results/agent-value" / stamp


def _resolve_executable(executable: Path) -> Path:
    if executable.is_absolute() or executable.parent != Path("."):
        return executable.resolve()
    resolved = shutil.which(str(executable))
    return Path(resolved).resolve() if resolved else executable


def _verification_python(executable: Path) -> Path:
    """Return an absolute path without dereferencing a virtualenv symlink."""
    return executable.absolute()


def _routing_gate_for_policy(adaptive_policy: str | None) -> RoutingGate:
    if adaptive_policy in {
        AdaptivePolicy.INJECTED_PACKET.value,
        AdaptivePolicy.INJECTED_RUNTIME.value,
    }:
        return RoutingGate.CONTEXT_OWNER
    return RoutingGate.AGENT_TOOL


def _select_tasks(args: argparse.Namespace, tasks: list[TaskSpec]) -> list[TaskSpec]:
    if args.smoke and args.task:
        raise ValueError("--smoke and --task cannot be combined")
    requested = set(SMOKE_TASK_IDS if args.smoke else args.task)
    if not requested:
        return tasks
    known = {task.id for task in tasks}
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError(f"unknown task id: {unknown[0]}")
    return [task for task in tasks if task.id in requested]


def _selected_repeats(args: argparse.Namespace) -> int:
    repeats = 1 if args.smoke else args.repeats
    if repeats <= 0:
        raise ValueError("--repeats must be positive")
    return repeats


def _cells(
    tasks: list[TaskSpec], conditions: list[Condition], repeats: int
) -> list[tuple[TaskSpec, Condition, int]]:
    cells: list[tuple[TaskSpec, Condition, int]] = []
    for repeat in range(1, repeats + 1):
        for index, task in enumerate(tasks):
            ordered = list(conditions)
            if len(ordered) == 2 and (index + repeat) % 2:
                ordered.reverse()
            cells.extend((task, condition, repeat) for condition in ordered)
    return cells


def _cell_id(task: TaskSpec, condition: Condition, repeat: int) -> str:
    return f"{task.id}__{condition.value}__r{repeat:02d}"


def _command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0] or None


def _git_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _git_remote(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    remote = result.stdout.strip()
    return remote or None


def _corpus_hash(tasks_file: Path, tasks: list[TaskSpec]) -> str:
    digest = hashlib.sha256()
    assets = [tasks_file.resolve()]
    assets.extend(
        path
        for task in tasks
        for path in (task.mutation_path.resolve(), task.grader_path.resolve())
    )
    assets = list(dict.fromkeys(assets))
    for path in assets:
        try:
            label = path.relative_to(tasks_file.resolve().parent)
        except ValueError:
            label = Path(path.name)
        digest.update(str(label).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _metadata(
    args: argparse.Namespace,
    tasks: list[TaskSpec],
    conditions: list[Condition],
    repeats: int,
) -> dict[str, Any]:
    tldrs_executable = args.tldrs_bin_dir / "tldrs"
    source_repo = args.source_repo.resolve()
    return {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluator_sha": _git_sha(REPO_ROOT),
        "source_repo": str(source_repo),
        "source_remote": _git_remote(source_repo),
        "source_sha": _git_sha(source_repo),
        "task_corpus_sha256": _corpus_hash(args.tasks_file, tasks),
        "task_ids": [task.id for task in tasks],
        "conditions": [condition.value for condition in conditions],
        "repeats": repeats,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "adaptive_policy": args.adaptive_policy,
        "timeout_seconds": args.timeout_seconds,
        "seed": args.seed,
        "codex_version": _command_version(
            [str(_resolve_executable(args.codex_executable)), "--version"]
        ),
        "tldrs_version": _command_version([str(tldrs_executable), "--version"]),
        "python_version": platform.python_version(),
        "host_os": platform.system(),
        "host_release": platform.release(),
        "host_arch": platform.machine(),
    }


def _load_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"run metadata does not exist: {path}")
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or raw.get("format_version") != FORMAT_VERSION:
        raise ValueError("unsupported or invalid run metadata")
    return raw


def _validate_resume(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    fields = (
        "evaluator_sha",
        "source_repo",
        "source_sha",
        "task_corpus_sha256",
        "task_ids",
        "conditions",
        "repeats",
        "model",
        "reasoning_effort",
        "adaptive_policy",
        "timeout_seconds",
        "seed",
    )
    mismatches = [field for field in fields if expected.get(field) != actual.get(field)]
    if mismatches:
        raise ValueError(f"resume configuration mismatch: {', '.join(mismatches)}")


def _load_outcomes(path: Path) -> list[RunOutcome]:
    if not path.exists():
        return []
    outcomes: list[RunOutcome] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text().splitlines(), 1):
        if not raw_line.strip():
            continue
        outcome = RunOutcome.from_dict(json.loads(raw_line))
        if outcome.cell_id in seen:
            raise ValueError(
                f"duplicate completed cell in outcomes line {line_number}: {outcome.cell_id}"
            )
        seen.add(outcome.cell_id)
        outcomes.append(outcome)
    return outcomes


def _append_outcome(path: Path, outcome: RunOutcome) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(outcome.to_dict(), sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _tasks_from_metadata(
    all_tasks: list[TaskSpec], metadata: dict[str, Any]
) -> list[TaskSpec]:
    by_id = {task.id: task for task in all_tasks}
    selected: list[TaskSpec] = []
    for task_id in metadata["task_ids"]:
        if task_id not in by_id:
            raise ValueError(f"metadata references unavailable task: {task_id}")
        selected.append(by_id[task_id])
    return selected


def _write_analysis(
    results_dir: Path,
    tasks: list[TaskSpec],
    outcomes: list[RunOutcome],
    repeats: int,
    seed: int,
    routing_gate: RoutingGate = RoutingGate.AGENT_TOOL,
) -> EvaluationAnalysis:
    analysis = analyze_outcomes(
        tasks,
        outcomes,
        expected_repeats=repeats,
        seed=seed,
        routing_gate=routing_gate,
    )
    write_reports(
        analysis,
        json_path=results_dir / "report.json",
        markdown_path=results_dir / "report.md",
    )
    return analysis


def _render_dry_run(
    args: argparse.Namespace,
    results_dir: Path,
    cells: list[tuple[TaskSpec, Condition, int]],
) -> None:
    print(f"Dry run: {len(cells)} cells")
    config = CodexRunConfig(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        timeout_s=args.timeout_seconds,
        codex_executable=_resolve_executable(args.codex_executable),
    )
    for task, condition, repeat in cells:
        cell = _cell_id(task, condition, repeat)
        command = build_codex_command(
            config,
            workspace=results_dir / "workspaces" / cell,
            prompt=task.prompt,
            output_last_message=results_dir / "messages" / f"{cell}.md",
        )
        print(f"{cell}: {shlex.join(command)}")


def _run_cell(
    args: argparse.Namespace,
    results_dir: Path,
    task: TaskSpec,
    condition: Condition,
    repeat: int,
) -> RunOutcome:
    cell = _cell_id(task, condition, repeat)
    config = CodexRunConfig(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        timeout_s=args.timeout_seconds,
        codex_executable=_resolve_executable(args.codex_executable),
    )
    environment = build_condition_environment(
        condition,
        tldrs_bin_dir=args.tldrs_bin_dir,
        adaptive_policy=args.adaptive_policy,
    )
    contamination: list[str] = []
    visible_tldrs = shutil.which("tldrs", path=environment.get("PATH"))
    if condition is Condition.BASELINE and visible_tldrs:
        contamination.append(f"tldrs executable visible at {visible_tldrs}")
    expects_agent_tool = args.adaptive_policy not in {
        AdaptivePolicy.INJECTED_PACKET.value,
        AdaptivePolicy.INJECTED_RUNTIME.value,
    }
    if condition is Condition.ADAPTIVE and expects_agent_tool and not visible_tldrs:
        contamination.append("tldrs executable is unavailable")

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.keep_workspaces:
        workspace = results_dir / "workspaces" / cell
    else:
        temporary = tempfile.TemporaryDirectory(prefix=f"tldrs-eval-{cell}-")
        workspace = Path(temporary.name) / "workspace"
    try:
        materialize_workspace(
            args.source_repo,
            task,
            condition,
            workspace,
            adaptive_policy=args.adaptive_policy,
            verification_python=_verification_python(args.grader_python),
        )
        process = run_codex(
            config,
            workspace=workspace,
            prompt=task.prompt,
            environment=environment,
            trace_path=results_dir / "traces" / f"{cell}.jsonl",
            output_last_message=results_dir / "messages" / f"{cell}.md",
        )
        (results_dir / "stderr").mkdir(parents=True, exist_ok=True)
        (results_dir / "stderr" / f"{cell}.log").write_text(process.stderr)
        patch = capture_patch(workspace)
        (results_dir / "patches").mkdir(parents=True, exist_ok=True)
        (results_dir / "patches" / f"{cell}.diff").write_bytes(patch)
        digest = patch_hash(workspace)
        owners = tuple(
            sorted(
                str(replacement.path)
                for replacement in load_replacements(task.mutation_path)
            )
        )
        changes = changed_paths(workspace)
        owner_set = set(owners)
        read_set = set(process.trace.metrics.unique_raw_read_paths)
        change_set = set(changes)
        owner_read_hits = len(owner_set & read_set)
        owner_change_hits = len(owner_set & change_set)
        grade = run_external_grader(
            task, workspace, python_executable=args.grader_python
        )
        (results_dir / "graders").mkdir(parents=True, exist_ok=True)
        (results_dir / "graders" / f"{cell}.stdout").write_text(grade.stdout)
        (results_dir / "graders" / f"{cell}.stderr").write_text(grade.stderr)
        return RunOutcome(
            task_id=task.id,
            condition=condition,
            repeat=repeat,
            agent_exit_code=process.exit_code,
            agent_timed_out=process.timed_out,
            elapsed_ms=process.elapsed_ms,
            patch_hash=digest,
            trace=process.trace.metrics,
            grade=grade,
            contaminated=bool(contamination),
            contamination_reasons=tuple(contamination),
            owner_paths=owners,
            changed_paths=changes,
            owner_read_precision=(
                owner_read_hits / len(read_set) if read_set else None
            ),
            owner_read_recall=(
                owner_read_hits / len(owner_set) if owner_set else None
            ),
            owner_change_precision=(
                owner_change_hits / len(change_set) if change_set else None
            ),
            owner_change_recall=(
                owner_change_hits / len(owner_set) if owner_set else None
            ),
        )
    finally:
        if temporary is not None:
            temporary.cleanup()


def _print_tasks(tasks: list[TaskSpec]) -> None:
    print(f"{len(tasks)} tasks")
    for task in tasks:
        eligibility = "eligible" if task.eligible_for_tldrs else "skip-control"
        print(f"{task.id}\t{task.category.value}\t{eligibility}\t{task.title}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.source_repo = args.source_repo.resolve()
        require_pilot_corpus = (
            args.tasks_file.resolve() == DEFAULT_TASKS_FILE.resolve()
        )
        all_tasks = load_agent_tasks(
            args.tasks_file, require_pilot_corpus=require_pilot_corpus
        )
        if args.list_tasks:
            _print_tasks(all_tasks)
            return 0
        results_dir = (args.results_dir or _default_results_dir()).resolve()
        outcomes_path = results_dir / "outcomes.jsonl"

        if args.report_only:
            metadata = _load_metadata(results_dir / "metadata.json")
            tasks = _tasks_from_metadata(all_tasks, metadata)
            if _corpus_hash(args.tasks_file, tasks) != metadata["task_corpus_sha256"]:
                raise ValueError("task corpus differs from the recorded run")
            outcomes = _load_outcomes(outcomes_path)
            analysis = _write_analysis(
                results_dir,
                tasks,
                outcomes,
                int(metadata["repeats"]),
                int(metadata["seed"]),
                _routing_gate_for_policy(metadata.get("adaptive_policy")),
            )
            print(f"Verdict: {analysis.verdict.value.upper()}")
            return 0

        tasks = _select_tasks(args, all_tasks)
        conditions = [Condition(value) for value in args.conditions]
        if len(set(conditions)) != len(conditions):
            raise ValueError("--conditions must not contain duplicates")
        repeats = _selected_repeats(args)
        routing_gate = _routing_gate_for_policy(args.adaptive_policy)
        cells = _cells(tasks, conditions, repeats)
        if args.dry_run:
            _render_dry_run(args, results_dir, cells)
            return 0

        expected_metadata = _metadata(args, tasks, conditions, repeats)
        metadata_path = results_dir / "metadata.json"
        if args.resume:
            actual_metadata = _load_metadata(metadata_path)
            _validate_resume(expected_metadata, actual_metadata)
        else:
            if results_dir.exists() and any(results_dir.iterdir()):
                raise ValueError(
                    f"results directory is not empty; use --resume: {results_dir}"
                )
            results_dir.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(
                json.dumps(expected_metadata, indent=2, sort_keys=True) + "\n"
            )

        outcomes = _load_outcomes(outcomes_path)
        completed = {outcome.cell_id for outcome in outcomes}
        skipped = 0
        for task, condition, repeat in cells:
            cell = _cell_id(task, condition, repeat)
            if cell in completed:
                skipped += 1
                continue
            print(f"RUN {cell}", flush=True)
            outcome = _run_cell(
                args, results_dir, task, condition, repeat
            )
            _append_outcome(outcomes_path, outcome)
            outcomes.append(outcome)
            completed.add(cell)
            print(
                f"DONE {cell} success={outcome.success} "
                f"tokens={outcome.trace.uncached_total_tokens} "
                f"tldrs={outcome.trace.tldrs_calls}",
                flush=True,
            )
            _write_analysis(
                results_dir,
                tasks,
                outcomes,
                repeats,
                args.seed,
                routing_gate,
            )

        analysis = _write_analysis(
            results_dir,
            tasks,
            outcomes,
            repeats,
            args.seed,
            routing_gate,
        )
        if skipped:
            print(f"Resume: skipped {skipped} completed cells")
        print(f"Verdict: {analysis.verdict.value.upper()}")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    return 2
