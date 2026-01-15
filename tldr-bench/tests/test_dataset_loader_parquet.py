from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from tldr_bench.datasets import load_dataset


def test_load_parquet_dataset(tmp_path: Path) -> None:
    rows = [
        {
            "instance_id": "swe-1",
            "problem_statement": "Fix the bug.",
        }
    ]
    table = pa.Table.from_pylist(rows)
    path = tmp_path / "sample.parquet"
    pq.write_table(table, path)

    instances = load_dataset(path, kind="swebench")
    assert instances[0].instance_id == "swe-1"
    assert instances[0].prompt == "Fix the bug."
