from pathlib import Path

import pytest

from tldr_bench.openhands import resolve_bench_dir


def test_resolve_bench_dir_env(monkeypatch, tmp_path):
    bench = tmp_path / "bench"
    bench.mkdir()
    monkeypatch.setenv("OH_BENCH_DIR", str(bench))
    assert resolve_bench_dir() == bench


def test_resolve_bench_dir_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("OH_BENCH_DIR", raising=False)
    vendor = tmp_path / "vendor" / "openhands-benchmarks"
    vendor.mkdir(parents=True)
    assert resolve_bench_dir(tmp_path) == vendor


def test_resolve_bench_dir_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("OH_BENCH_DIR", raising=False)
    with pytest.raises(FileNotFoundError):
        resolve_bench_dir(tmp_path)
