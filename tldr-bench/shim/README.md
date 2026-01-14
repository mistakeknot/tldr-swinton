# CLI Shim

Start the shim server:

```bash
PYTHONPATH=tldr-bench uv run --with fastapi --with uvicorn python tldr-bench/tldr_bench/shim/server.py --config tldr-bench/shim/config.toml
```

Optional JSONL logging (add to `config.toml`):

```toml
log_path = "/tmp/tldr-shim.jsonl"
```

Example OpenHands LLM config:

```json
{
  "model": "codex:default",
  "base_url": "http://127.0.0.1:8089",
  "api_key": "dummy"
}
```

Use `claude:default` to route to the Claude Code CLI.
