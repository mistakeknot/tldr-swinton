# OpenHands Benchmarks Setup

OpenHands benchmarks are tracked as a git submodule at:

- `tldr-bench/vendor/openhands-benchmarks`

Initialize/update:

```bash
git submodule update --init --recursive
```

The upstream repo expects a local Agent SDK and uses uv for installation.
Follow its README for `uv sync` setup inside the submodule.

If you keep the benchmarks elsewhere, set:

```bash
export OH_BENCH_DIR=/path/to/OpenHands/benchmarks
```
