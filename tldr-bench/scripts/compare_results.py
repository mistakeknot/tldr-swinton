from __future__ import annotations

import argparse
import json
from pathlib import Path

from tldr_bench.compare_results import compare_results


def _format_line(values: list[str], widths: list[int]) -> str:
    return "  ".join(value.ljust(widths[i]) for i, value in enumerate(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--variants", nargs="+", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = compare_results(
        Path(args.baseline),
        [Path(path) for path in args.variants],
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
