from __future__ import annotations

import argparse
import json
from pathlib import Path

from tldr_bench.compare_results import compare_results

PRESET_TRACKS = {
    "dataset-context": {
        "baseline": "official_datasets_context_baselines.jsonl",
        "variants": [
            "official_datasets_context_symbolkite.jsonl",
            "official_datasets_context_cassette.jsonl",
            "official_datasets_context_coveragelens.jsonl",
        ],
    },
}


def _format_line(values: list[str], widths: list[int]) -> str:
    return "  ".join(value.ljust(widths[i]) for i, value in enumerate(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline")
    parser.add_argument("--variants", nargs="+")
    parser.add_argument("--track", choices=sorted(PRESET_TRACKS))
    parser.add_argument("--results-dir", default="tldr-bench/results")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.track and not (args.baseline or args.variants):
        preset = PRESET_TRACKS[args.track]
        results_dir = Path(args.results_dir)
        baseline_path = results_dir / preset["baseline"]
        variant_paths = [results_dir / name for name in preset["variants"]]
    else:
        if not args.baseline or not args.variants:
            parser.error("the following arguments are required: --baseline, --variants")
        baseline_path = Path(args.baseline)
        variant_paths = [Path(path) for path in args.variants]

    results = compare_results(
        baseline_path,
        variant_paths,
    )

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    for result in results:
        print(f"variant: {result['variant']}")
        print(f"tasks: {result['tasks']}")
        headers = ["metric", "baseline", "variant", "savings", "savings_pct"]
        rows = [headers]
        for metric, values in result["metrics"].items():
            pct = values["savings_pct"]
            rows.append(
                [
                    metric,
                    str(int(values["baseline"])),
                    str(int(values["variant"])),
                    str(int(values["savings"])),
                    f"{pct:.1f}%" if pct is not None else "n/a",
                ]
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
        for row in rows:
            print(_format_line(row, widths))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
