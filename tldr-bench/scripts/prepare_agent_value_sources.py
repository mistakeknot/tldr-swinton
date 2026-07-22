#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tldr_bench.agent_eval.sources import (  # noqa: E402
    load_source_specs,
    prepare_sources,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare immutable external sources for agent-value evaluation."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    prepared = prepare_sources(load_source_specs(args.manifest), args.output_dir)
    for source_id, path in prepared.items():
        print(f"{source_id}\t{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
