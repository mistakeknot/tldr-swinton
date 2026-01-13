import argparse

from tldr_bench.runners.openhands_runner import run_task


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--help-variants", action="store_true")
    parser.add_argument("--tasks", default=None)
    parser.add_argument("--variant", default=None)
    args = parser.parse_args()
    if args.help_variants:
        print("baselines, difflens, symbolkite, cassette, coveragelens")
        return 0
    if args.tasks and args.variant:
        run_task({"id": "placeholder"}, args.variant)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
