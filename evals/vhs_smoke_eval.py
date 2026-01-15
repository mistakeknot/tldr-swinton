from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def _first_nonempty_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test tldrs-vhs integration")
    parser.add_argument(
        "--entry",
        default="src/tldr_swinton/engines/symbolkite.py:get_relevant_context",
        help="Entry point for tldrs context",
    )
    parser.add_argument("--project", default=".", help="Project root")
    parser.add_argument("--budget", type=int, default=2000)
    args = parser.parse_args()

    project = str(Path(args.project).resolve())

    cmd_store = [
        "tldrs",
        "context",
        args.entry,
        "--project",
        project,
        "--budget",
        str(args.budget),
        "--output",
        "vhs",
    ]
    store = _run(cmd_store)
    if store.returncode != 0:
        print("VHS store failed. Is tldrs-vhs installed?", file=sys.stderr)
        sys.stderr.write(store.stderr)
        return 2

    ref_line = _first_nonempty_line(store.stdout)
    if not ref_line or not ref_line.startswith("vhs://"):
        print("Failed to parse vhs:// ref from output", file=sys.stderr)
        sys.stderr.write(store.stdout)
        return 1

    cmd_expand = [
        "tldrs",
        "context",
        args.entry,
        "--project",
        project,
        "--include",
        ref_line,
    ]
    expanded = _run(cmd_expand)
    if expanded.returncode != 0:
        print("VHS include failed", file=sys.stderr)
        sys.stderr.write(expanded.stderr)
        return 1

    preview_len = len(store.stdout)
    expanded_len = len(expanded.stdout)
    if expanded_len == 0:
        print("Expanded output was empty", file=sys.stderr)
        return 1

    if expanded_len <= preview_len:
        print(
            "Warning: expanded output not larger than preview; check VHS config",
            file=sys.stderr,
        )

    print("VHS smoke test ok")
    print(f"ref: {ref_line}")
    print(f"preview_bytes: {preview_len}")
    print(f"expanded_bytes: {expanded_len}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
