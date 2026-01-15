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


def test_longbench_uses_context_and_question() -> None:
    record = {
        "_id": "lb-2",
        "context": "Context blob.",
        "question": "What is the answer?",
        "answer": "42",
    }
    inst = normalize_record(record)
    assert inst.instance_id == "lb-2"
    assert inst.prompt == "Context blob.\n\nWhat is the answer?"
