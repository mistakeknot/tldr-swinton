from __future__ import annotations

import argparse
import json
from urllib import request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8089")
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "stream": False,
    }
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
