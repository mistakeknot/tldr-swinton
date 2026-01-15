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

## Module Guidance (Frontier Runs)

When the agent needs context, prefer these tools in order:

```bash
# 1) Diff-first context (recent changes)
tldrs diff-context --project . --budget 2000

# 2) Symbol-level context (call graph + deps)
tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact

# 3) Structure / extract (file or folder overview)
tldrs structure src/
tldrs extract path/to/file.py

# 4) Semantic search (requires index)
tldrs index .
tldrs find "authentication logic"

# 5) Deep analysis helpers (optional)
tldrs slice <file> <func> <line>
tldrs cfg <file> <function>
tldrs dfg <file> <function>
```

## VHS Output (Optional)

If `tldrs-vhs` is installed, you can store large outputs as `vhs://` refs:

```bash
tldrs context <entry> --project . --output vhs
tldrs context <entry> --project . --include vhs://<hash>
```

If the CLI can't find `tldrs-vhs` in non-interactive shells, set:

```bash
export TLDRS_VHS_CMD="$HOME/tldrs-vhs/.venv/bin/tldrs-vhs"
```
