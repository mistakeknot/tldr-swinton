import json
from pathlib import Path

from tldr_bench.datasets.repobench import normalize_record


def test_repobench_prompt():
    fixture = Path(__file__).parent / "fixtures" / "datasets" / "repobench.json"
    record = json.loads(fixture.read_text(encoding="utf-8"))[0]
    inst = normalize_record(record)
    assert inst.instance_id == "rb-1"
    assert inst.prompt.startswith("def foo")
    assert inst.dataset == "repobench"
    assert inst.split == "test"
    assert inst.metadata.get("completion") == "print(foo())"


def test_repobench_missing_id_uses_repo_fields():
    record = {
        "context": "def foo():\\n    return 1",
        "repo_name": "example/repo",
        "file_path": "foo.py",
        "level": "cross_file",
        "next_line": "print(foo())",
    }
    inst = normalize_record(record)
    assert inst.instance_id.startswith("example/repo:foo.py")
    assert inst.prompt.startswith("def foo")
