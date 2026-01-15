import json
from pathlib import Path

from tldr_bench.datasets.longbench import normalize_record


def test_longbench_prompt():
    fixture = Path(__file__).parent / "fixtures" / "datasets" / "longbench.json"
    record = json.loads(fixture.read_text(encoding="utf-8"))[0]
    inst = normalize_record(record)
    assert inst.instance_id == "code:lb-1"
    assert inst.prompt == "Summarize the function behavior."
    assert inst.dataset == "longbench"
    assert inst.split == "test"
    assert inst.metadata.get("output") == "It returns 1."
