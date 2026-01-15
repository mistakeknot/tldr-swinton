from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from . import commit0 as commit0_loader
from . import longbench as longbench_loader
from . import repobench as repobench_loader
from . import swebench as swebench_loader
from .schema import BenchInstance


def _read_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("pyarrow is required to read parquet datasets") from exc
        table = pq.read_table(path)
        return table.to_pylist()
    if path.suffix.lower() == ".jsonl":
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]
    raise ValueError("Unsupported dataset format: expected list or jsonl")


def _detect_kind(path: Path, records: list[dict[str, Any]]) -> str | None:
    name = path.name.lower()
    if "swebench" in name:
        return "swebench"
    if "commit0" in name:
        return "commit0"
    if "repobench" in name:
        return "repobench"
    if "longbench" in name:
        return "longbench"
    for record in records:
        if "problem_statement" in record or "test_patch" in record:
            return "swebench"
        if "repo_name" in record or "function_signature" in record or "tests" in record:
            return "commit0"
        if "completion" in record or "cross_file" in record:
            return "repobench"
        if "dataset" in record and ("input" in record or "output" in record):
            return "longbench"
    return None


def load_dataset(path: Path, kind: str | None = None) -> list[BenchInstance]:
    resolved = path.expanduser().resolve()
    records = _read_records(resolved)
    dataset_kind = kind or _detect_kind(resolved, records)
    if dataset_kind is None:
        raise ValueError(f"Could not detect dataset kind for {resolved}")
    if dataset_kind == "swebench":
        return [swebench_loader.normalize_record(record) for record in records]
    if dataset_kind == "commit0":
        return [commit0_loader.normalize_record(record) for record in records]
    if dataset_kind == "repobench":
        return [repobench_loader.normalize_record(record) for record in records]
    if dataset_kind == "longbench":
        return [longbench_loader.normalize_record(record) for record in records]
    raise ValueError(f"Unsupported dataset kind: {dataset_kind}")


def select_instances(
    instances: Iterable[BenchInstance],
    instance_ids: list[str] | None,
) -> list[BenchInstance]:
    if not instance_ids:
        return list(instances)
    wanted = {item.strip() for item in instance_ids if item.strip()}
    return [inst for inst in instances if inst.instance_id in wanted]
