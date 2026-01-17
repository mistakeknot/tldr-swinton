import json

from tldr_swinton import mcp_server


def test_mcp_context_returns_contextpack_json(tmp_path) -> None:
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n")
    fake = {
        "status": "ok",
        "result": {
            "slices": [{"id": "m.py:foo", "signature": "def foo()", "code": None}],
            "signatures_only": [],
        },
    }
    result = mcp_server._format_context_result(fake, "json")
    payload = json.loads(result)
    assert "slices" in payload
    assert payload["slices"]
