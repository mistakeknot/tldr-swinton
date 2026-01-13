from tldr_bench.shim.adapter import assemble_prompt, resolve_model_command


def test_assemble_prompt_basic():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Do thing"},
    ]
    prompt = assemble_prompt(messages)
    assert "SYSTEM:" in prompt
    assert "USER:" in prompt
    assert "ASSISTANT:" in prompt
    assert "Do thing" in prompt


def test_resolve_model_command():
    model_map = {"codex": "codex", "claude": "claude"}
    assert resolve_model_command("codex:default", model_map) == "codex"
    assert resolve_model_command("claude:sonnet", model_map) == "claude"
