from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
from collections.abc import Mapping
from pathlib import Path

import yaml

from .schema import Condition, GradeResult, Replacement, TaskSpec


_EVALUATOR_EXCLUSIONS = (
    Path(".codex"),
    Path(".claude-plugin"),
    Path("AGENTS.md"),
    Path("CLAUDE.md"),
    Path("tldr-bench/agent_eval"),
    Path("tldr-bench/tldr_bench/agent_eval"),
    Path("tldr-bench/tldr_bench/tasks/agent_value.yaml"),
    Path("tldr-bench/tests/test_agent_value_tasks.py"),
    Path("tldr-bench/tests/test_agent_value_cli.py"),
)

_BASELINE_GUIDANCE = """# Evaluation condition: baseline

Solve the user's coding task using the standard shell and file tools available in this repository.

Do not use tldrs, tldr-swinton, or tldr-mcp in this condition.
Run relevant tests before reporting completion.
"""

_ADAPTIVE_GUIDANCE = """# Evaluation condition: adaptive tldrs

Solve the user's coding task and run relevant tests before reporting completion.

Use tldrs when it materially narrows the next read: unfamiliar areas, cross-file relationships, semantic discovery, non-trivial diffs, or dependency-sensitive edits. Prefer compact commands such as `tldrs context`, `tldrs diff-context`, `tldrs structure`, or `tldrs find` before broad raw reads.

Skip tldrs when the exact target is already known, the task is a small scoped edit, or the available context already identifies the required lines.
"""

_TEST_COUNT = re.compile(r"EVAL_TESTS\s+passed=(\d+)\s+total=(\d+)")


def load_replacements(path: Path) -> tuple[Replacement, ...]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or set(raw) != {"replacements"}:
        raise ValueError("mutation file must contain only a replacements list")
    items = raw["replacements"]
    if not isinstance(items, list):
        raise ValueError("replacements must be a list")

    replacements: list[Replacement] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"path", "old", "new"}:
            raise ValueError("each replacement requires path, old, and new")
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
            raise ValueError("replacement path must be a relative workspace path")
        if not isinstance(item["old"], str) or not isinstance(item["new"], str):
            raise ValueError("replacement old and new values must be strings")
        replacements.append(Replacement(relative, item["old"], item["new"]))
    return tuple(replacements)


def _extract_git_archive(source_repo: Path, destination: Path) -> None:
    result = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=source_repo,
        check=True,
        capture_output=True,
    )
    destination.mkdir(parents=True)
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"archive path escapes workspace: {member.name}")
            archive.extract(member, destination)


def _remove_evaluator_surface(destination: Path) -> None:
    for relative in _EVALUATOR_EXCLUSIONS:
        target = destination / relative
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()


def _apply_replacements(destination: Path, replacements: tuple[Replacement, ...]) -> None:
    root = destination.resolve()
    for replacement in replacements:
        target = (destination / replacement.path).resolve()
        if not target.is_relative_to(root):
            raise ValueError("replacement path must stay inside workspace")
        if not target.is_file():
            raise ValueError(f"replacement target does not exist: {replacement.path}")
        text = target.read_text()
        matches = text.count(replacement.old)
        if matches != 1:
            raise ValueError(
                f"replacement {replacement.path} expected exactly one match, found {matches}"
            )
        target.write_text(text.replace(replacement.old, replacement.new, 1))


def _write_condition_guidance(destination: Path, condition: Condition) -> None:
    guidance = (
        _BASELINE_GUIDANCE
        if condition is Condition.BASELINE
        else _ADAPTIVE_GUIDANCE
    )
    (destination / "AGENTS.md").write_text(guidance)


def _initialize_history_free_repo(destination: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=destination, check=True)
    subprocess.run(["git", "add", "-A"], cwd=destination, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=tldrs-agent-eval",
            "-c",
            "user.email=tldrs-agent-eval@example.invalid",
            "commit",
            "-qm",
            "agent evaluation task base",
        ],
        cwd=destination,
        check=True,
    )


def materialize_workspace(
    source_repo: Path,
    task: TaskSpec,
    condition: Condition,
    destination: Path,
) -> Path:
    if destination.exists():
        raise ValueError(f"workspace destination already exists: {destination}")
    _extract_git_archive(source_repo.resolve(), destination)
    _remove_evaluator_surface(destination)
    _apply_replacements(destination, load_replacements(task.mutation_path))
    _write_condition_guidance(destination, condition)
    _initialize_history_free_repo(destination)
    return destination


def build_condition_environment(
    condition: Condition,
    base: Mapping[str, str] | None = None,
    *,
    tldrs_bin_dir: Path = Path("/Users/sma/.local/bin"),
) -> dict[str, str]:
    environment = dict(os.environ if base is None else base)
    current_path = environment.get("PATH", "")
    tldrs_dir = tldrs_bin_dir.resolve()
    parts = [
        part
        for part in current_path.split(os.pathsep)
        if part and Path(part).resolve() != tldrs_dir
    ]
    if condition is Condition.ADAPTIVE:
        parts.insert(0, str(tldrs_dir))
        environment["TLDRS_ENABLED"] = "1"
        environment.pop("TLDRS_DISABLED", None)
    else:
        environment["TLDRS_DISABLED"] = "1"
        environment.pop("TLDRS_ENABLED", None)
    environment["TLDRS_EVAL_CONDITION"] = condition.value
    environment["PATH"] = os.pathsep.join(parts)
    return environment


def run_external_grader(
    task: TaskSpec,
    workspace: Path,
    *,
    python_executable: Path,
) -> GradeResult:
    environment = dict(os.environ)
    environment["AGENT_EVAL_WORKSPACE"] = str(workspace.resolve())
    try:
        result = subprocess.run(
            [str(python_executable), str(task.grader_path), str(workspace.resolve())],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
            timeout=task.grader_timeout_s,
            env=environment,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nexternal grader timed out"

    match = _TEST_COUNT.search("\n".join([stdout, stderr]))
    tests_passed = int(match.group(1)) if match else None
    tests_total = int(match.group(2)) if match else None
    return GradeResult(
        passed=exit_code == 0,
        exit_code=exit_code,
        tests_passed=tests_passed,
        tests_total=tests_total,
        stdout=stdout,
        stderr=stderr,
    )


def patch_hash(workspace: Path) -> str:
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
    ).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=workspace,
        check=True,
        capture_output=True,
    ).stdout
    payload = bytearray(diff)
    for raw_path in sorted(part for part in untracked.split(b"\0") if part):
        relative = raw_path.decode()
        payload.extend(b"\0UNTRACKED\0")
        payload.extend(raw_path)
        payload.extend(b"\0")
        payload.extend((workspace / relative).read_bytes())
    return hashlib.sha256(payload).hexdigest()
