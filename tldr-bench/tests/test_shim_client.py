from tldr_bench.shim.client import build_payload, build_prompt


def test_build_prompt_with_context():
    prompt = build_prompt("Do the thing", "CTX")
    assert prompt.startswith("Context:\nCTX")
    assert "Task:\nDo the thing" in prompt


def test_build_payload():
    payload = build_payload("codex:default", "hi")
    assert payload["model"] == "codex:default"
    assert payload["messages"][0]["content"] == "hi"
