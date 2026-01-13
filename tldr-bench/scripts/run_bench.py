import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--help-variants", action="store_true")
    args = parser.parse_args()
    if args.help_variants:
        print("baselines, difflens, symbolkite, cassette, coveragelens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
