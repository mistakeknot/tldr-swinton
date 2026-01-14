from pathlib import Path

from tldr_bench.summary import summarize_jsonl


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    summary = summarize_jsonl(Path(args.path))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
