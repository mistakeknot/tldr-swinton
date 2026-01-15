import json
from pathlib import Path

from tldr_bench.datasets import load_dataset, select_instances


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_load_swebench_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "swebench_lite.jsonl"
    _write_jsonl(
        path,
        [
            {
                "instance_id": "django__django-123",
                "repo": "django/django",
                "base_commit": "abc",
                "problem_statement": "Fix bug",
            }
        ],
    )
    instances = load_dataset(path)
    assert len(instances) == 1
    inst = instances[0]
    assert inst.dataset == "swebench"
    assert inst.instance_id == "django__django-123"
    assert inst.prompt == "Fix bug"


def test_load_commit0_json_with_kind(tmp_path: Path) -> None:
    path = tmp_path / "commit0.json"
    _write_json(
        path,
        [
            {
                "task_id": "commit0-1",
                "repo": "commit0/repo",
                "base_commit": "def",
                "instruction": "Implement function",
                "tests": ["test_one"],
            }
        ],
    )
    instances = load_dataset(path, kind="commit0")
    assert len(instances) == 1
    inst = instances[0]
    assert inst.dataset == "commit0"
    assert inst.instance_id == "commit0-1"
    assert inst.prompt == "Implement function"


def test_select_instances_filters(tmp_path: Path) -> None:
    path = tmp_path / "swebench_sample.jsonl"
    _write_jsonl(
        path,
        [
            {"instance_id": "one", "problem_statement": "A"},
            {"instance_id": "two", "problem_statement": "B"},
        ],
    )
    instances = load_dataset(path)
    selected = select_instances(instances, ["two"])
    assert [inst.instance_id for inst in selected] == ["two"]
