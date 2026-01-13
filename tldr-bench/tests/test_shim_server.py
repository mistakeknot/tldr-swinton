from fastapi.testclient import TestClient

from tldr_bench.shim.server import create_app


def test_models_endpoint():
    app = create_app({"model_map": {"codex": "codex"}})
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


def test_chat_completion_basic():
    app = create_app({"model_map": {"codex": "codex"}})
    app.state.runner = lambda prompt, cmd, timeout: "ok"
    client = TestClient(app)
    payload = {
        "model": "codex:default",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "ok"
