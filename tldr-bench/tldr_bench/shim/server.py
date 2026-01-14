from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import tomllib

from tldr_bench.shim.adapter import assemble_prompt, resolve_model_command
from tldr_bench.metrics import count_tokens


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"port": 8089, "timeout_seconds": 120, "model_map": {"codex": "codex", "claude": "claude"}}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    model_map = data.get("model_map", {})
    return {
        "port": data.get("port", 8089),
        "timeout_seconds": data.get("timeout_seconds", 120),
        "model_map": model_map,
    }


def run_cli(prompt: str, command: str, timeout_seconds: int) -> str:
    result = subprocess.run(
        [command, prompt],
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {command}")
    return result.stdout


def create_app(config: dict[str, Any]) -> FastAPI:
    app = FastAPI()
    app.state.config = config
    app.state.runner = run_cli

    @app.get("/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    def models() -> dict[str, Any]:
        model_map = app.state.config.get("model_map", {})
        return {"data": [{"id": key} for key in model_map.keys()]}

    @app.post("/v1/chat/completions")
    def chat(payload: dict[str, Any]) -> JSONResponse:
        if payload.get("stream"):
            raise HTTPException(status_code=400, detail="streaming not supported")
        model = payload.get("model")
        if not model:
            raise HTTPException(status_code=400, detail="model is required")
        messages = payload.get("messages", [])
        prompt = assemble_prompt(messages)
        model_map = app.state.config.get("model_map", {})
        command = resolve_model_command(model, model_map)
        timeout_seconds = int(app.state.config.get("timeout_seconds", 120))
        start = time.time()
        try:
            output = app.state.runner(prompt, command, timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc))
        duration = time.time() - start
        prompt_tokens = count_tokens(prompt, model=model)
        completion_tokens = count_tokens(output, model=model)
        response = {
            "id": f"shim-{int(start * 1000)}",
            "object": "chat.completion",
            "created": int(start),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": output},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "shim": {"elapsed_ms": int(duration * 1000)},
        }
        return JSONResponse(content=response)

    return app


def main() -> int:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    config = load_config(Path(args.config) if args.config else None)
    uvicorn.run(create_app(config), host="127.0.0.1", port=int(config["port"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
