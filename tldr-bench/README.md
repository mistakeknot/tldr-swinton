# tldr-bench

Token-efficiency benchmarks for tldr-swinton using the OpenHands evaluation harness.

## Quickstart (uv)

```bash
uv venv
uv pip install -e .
python scripts/run_bench.py --help
python scripts/run_bench.py --tasks curated --list-tasks
```

## OpenHands Benchmarks (required for real runs)

This repo includes the OpenHands benchmarks as a submodule:

```bash
git submodule update --init --recursive
```

Follow the upstream instructions inside `tldr-bench/vendor/openhands-benchmarks`
to install its dependencies (they use `uv sync` and a local Agent SDK).

Set `OH_BENCH_DIR` if you keep the benchmarks elsewhere:

```bash
export OH_BENCH_DIR=/path/to/OpenHands/benchmarks
```
