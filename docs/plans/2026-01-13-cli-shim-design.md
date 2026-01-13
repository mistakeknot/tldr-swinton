# CLI Shim Design (Codex/Claude Code)

Date: 2026-01-13

## Overview
Provide a local HTTP shim that exposes an OpenAI-compatible API and shells out to `codex` or `claude` per request. This lets the OpenHands benchmarks run without paid API usage by reusing local CLI subscriptions.

## Architecture & Request Flow
- HTTP server exposes:
  - `POST /v1/chat/completions`
  - `GET /v1/models`
  - optional `GET /v1/health`
- Single-threaded request handling (spawn-per-request) for reproducibility.
- Prompt assembly concatenates system/user/assistant messages with clear delimiters.
- Model routing by `model` prefix (e.g., `codex:*` → `codex`, `claude:*` → `claude`).
- Optional model alias mapping via config file.

## CLI Invocation
- Spawn `codex` or `claude` with a non-interactive prompt flag.
- Enforce per-request timeout (default 120s).
- Reject streaming requests with a 400 error (for now).
- Capture stdout as model response; capture stderr + exit code on failures.

## Logging
- JSONL logs of each request:
  - request_id, model, prompt_bytes
  - elapsed_ms, exit_code, status
  - response_bytes, error (if any)
- Logs live under `tldr-bench/results/` for correlation with benchmark outputs.

## Integration with OpenHands
- `.llm_config/*.json` points to `http://localhost:<port>` with dummy API key.
- Model strings like `codex:default` or `claude:default` route in shim.
- No changes required to OpenHands harness.

## Testing
- Unit tests for prompt assembly + model routing.
- Fake CLI executable for test runs (echoes input).
- Health endpoint check.

## Next Steps
- Implement shim in `tldr-bench/shim/` with config file.
- Add tests under `tldr-bench/tests/`.
- Provide example `.llm_config` for OpenHands.
