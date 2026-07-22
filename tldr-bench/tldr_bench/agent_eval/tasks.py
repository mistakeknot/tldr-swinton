from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schema import TaskCategory, TaskSpec


_REQUIRED_FIELDS = {
    "id",
    "title",
    "category",
    "eligible_for_tldrs",
    "prompt",
    "mutation",
    "grader",
}
_OPTIONAL_FIELDS = {"grader_timeout_s", "verification_command"}


def _resolve_asset(base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty path")
    path = (base / value).resolve()
    if not path.is_file():
        raise ValueError(f"{label} file does not exist: {path}")
    return path


def _parse_task(raw: Any, base: Path) -> TaskSpec:
    if not isinstance(raw, dict):
        raise ValueError("each agent evaluation task must be a mapping")
    missing = _REQUIRED_FIELDS - raw.keys()
    if missing:
        raise ValueError(f"task is missing required fields: {sorted(missing)}")
    unknown = raw.keys() - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
    if unknown:
        raise ValueError(f"task has unknown fields: {sorted(unknown)}")

    try:
        category = TaskCategory(raw["category"])
    except ValueError as exc:
        raise ValueError(f"unknown task category: {raw['category']}") from exc
    eligible = raw["eligible_for_tldrs"]
    if not isinstance(eligible, bool):
        raise ValueError("eligible_for_tldrs must be a boolean")
    if category is TaskCategory.NEGATIVE_CONTROL and eligible:
        raise ValueError("negative controls must be ineligible for tldrs")

    mutation_path = _resolve_asset(base, raw["mutation"], "mutation")
    grader_path = _resolve_asset(base, raw["grader"], "grader")
    prompt = raw["prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be non-empty")
    hidden_names = {mutation_path.name, grader_path.name}
    if any(name in prompt for name in hidden_names):
        raise ValueError("prompt leaks hidden asset path")

    task_id = raw["id"]
    title = raw["title"]
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task id must be non-empty")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("task title must be non-empty")
    timeout = raw.get("grader_timeout_s", 120)
    if not isinstance(timeout, int) or timeout <= 0:
        raise ValueError("grader_timeout_s must be a positive integer")
    verification_command = raw.get("verification_command")
    if verification_command is not None and (
        not isinstance(verification_command, str) or not verification_command.strip()
    ):
        raise ValueError("verification_command must be a non-empty string")

    return TaskSpec(
        id=task_id,
        title=title,
        category=category,
        eligible_for_tldrs=eligible,
        prompt=prompt,
        mutation_path=mutation_path,
        grader_path=grader_path,
        verification_command=verification_command,
        grader_timeout_s=timeout,
    )


def load_agent_tasks(
    path: Path, *, require_pilot_corpus: bool = False
) -> list[TaskSpec]:
    task_path = path.resolve()
    raw_tasks = yaml.safe_load(task_path.read_text())
    if not isinstance(raw_tasks, list):
        raise ValueError("agent evaluation task file must contain a list")

    tasks = [_parse_task(raw, task_path.parent) for raw in raw_tasks]
    ids = [task.id for task in tasks]
    duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate task id: {duplicates[0]}")

    if require_pilot_corpus:
        if len(tasks) != 12:
            raise ValueError("pilot corpus requires exactly 12 tasks")
        counts = {
            category: sum(task.category is category for task in tasks)
            for category in TaskCategory
        }
        if any(count != 3 for count in counts.values()):
            raise ValueError("pilot corpus requires three tasks in each category")
    return tasks
