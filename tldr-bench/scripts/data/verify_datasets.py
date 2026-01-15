from __future__ import annotations

import argparse
from pathlib import Path

from tldr_bench.data import verify_dataset_manifests


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify vendored dataset manifests")
    parser.add_argument("--root", default=None, help="Dataset root (defaults to tldr-bench/data)")
    args = parser.parse_args()

    root = Path(args.root).expanduser() if args.root else None
    errors = verify_dataset_manifests(root)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
