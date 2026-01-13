import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="results")
    _ = parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
