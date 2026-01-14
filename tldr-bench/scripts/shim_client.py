from __future__ import annotations

import argparse
import json
from urllib import request

from tldr_bench.shim.client import build_context, build_payload, build_prompt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8089")
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--context-entry", default=None)
    parser.add_argument("--context-format", default="text")
    parser.add_argument("--context-depth", type=int, default=2)
    parser.add_argument("--context-budget", type=int, default=None)
    args = parser.parse_args()

    context = None
    if args.context_entry:
        context = build_context(
            args.project_root,
            args.context_entry,
            args.context_format,
            args.context_depth,
            args.context_budget,
        )
    prompt = build_prompt(args.prompt, context)
    payload = build_payload(args.model, prompt)
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{args.base_url}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
