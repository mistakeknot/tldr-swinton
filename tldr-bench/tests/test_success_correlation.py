"""Tests for success correlation metrics."""

import json
import tempfile
from pathlib import Path

import pytest

from tldr_bench.success_correlation import (
    CorrelationReport,
    SuccessCorrelator,
    TaskOutcome,
    VariantStats,
)


class TestTaskOutcome:
    def test_token_savings(self):
        outcome = TaskOutcome(
            task_id="test-1",
            variant="tldrs",
            success=True,
            tokens_used=1000,
            baseline_tokens=10000,
        )
        assert outcome.token_savings == 0.9  # 90% savings

    def test_token_savings_no_baseline(self):
        outcome = TaskOutcome(
            task_id="test-1",
            variant="tldrs",
            success=True,
            tokens_used=1000,
            baseline_tokens=None,
        )
        assert outcome.token_savings == 0.0

    def test_compression_ratio(self):
        outcome = TaskOutcome(
            task_id="test-1",
            variant="tldrs",
            success=True,
            tokens_used=1000,
            baseline_tokens=10000,
        )
        assert outcome.compression_ratio == 10.0

    def test_to_dict(self):
        outcome = TaskOutcome(
            task_id="test-1",
            variant="tldrs",
            success=True,
            tokens_used=1000,
            baseline_tokens=10000,
        )
        d = outcome.to_dict()
        assert d["task_id"] == "test-1"
        assert d["variant"] == "tldrs"
        assert d["success"] is True
        assert d["token_savings"] == 0.9


class TestSuccessCorrelator:
    def test_record_single(self):
        correlator = SuccessCorrelator()
        correlator.record(
            TaskOutcome(
                task_id="test-1",
                variant="baseline",
                success=True,
                tokens_used=10000,
            )
        )
        assert len(correlator._outcomes) == 1

    def test_record_batch(self):
        correlator = SuccessCorrelator()
        outcomes = [
            TaskOutcome(task_id="test-1", variant="baseline", success=True, tokens_used=10000),
            TaskOutcome(task_id="test-2", variant="baseline", success=False, tokens_used=8000),
        ]
        correlator.record_batch(outcomes)
        assert len(correlator._outcomes) == 2

    def test_compute_correlation_empty(self):
        correlator = SuccessCorrelator()
        report = correlator.compute_correlation()
        assert report.sample_size == 0
        assert "No data" in report.interpretation

    def test_compute_correlation_single_variant(self):
        correlator = SuccessCorrelator()
        correlator.record_batch(
            [
                TaskOutcome(task_id="1", variant="tldrs", success=True, tokens_used=1000),
                TaskOutcome(task_id="2", variant="tldrs", success=True, tokens_used=1500),
                TaskOutcome(task_id="3", variant="tldrs", success=False, tokens_used=2000),
            ]
        )
        report = correlator.compute_correlation()
        assert report.sample_size == 3
        assert len(report.variants) == 1
        assert report.variants[0].success_rate == pytest.approx(2 / 3)

    def test_compute_correlation_two_variants(self):
        correlator = SuccessCorrelator()
        # Baseline: 2/3 success, high tokens
        # TLDRS: 2/3 success, low tokens
        correlator.record_batch(
            [
                TaskOutcome(
                    task_id="1",
                    variant="baseline",
                    success=True,
                    tokens_used=10000,
                    baseline_tokens=10000,
                ),
                TaskOutcome(
                    task_id="2",
                    variant="baseline",
                    success=True,
                    tokens_used=10000,
                    baseline_tokens=10000,
                ),
                TaskOutcome(
                    task_id="3",
                    variant="baseline",
                    success=False,
                    tokens_used=10000,
                    baseline_tokens=10000,
                ),
                TaskOutcome(
                    task_id="1",
                    variant="tldrs-context",
                    success=True,
                    tokens_used=1000,
                    baseline_tokens=10000,
                ),
                TaskOutcome(
                    task_id="2",
                    variant="tldrs-context",
                    success=True,
                    tokens_used=1500,
                    baseline_tokens=10000,
                ),
                TaskOutcome(
                    task_id="3",
                    variant="tldrs-context",
                    success=False,
                    tokens_used=2000,
                    baseline_tokens=10000,
                ),
            ]
        )
        report = correlator.compute_correlation()
        assert report.sample_size == 6
        assert len(report.variants) == 2

    def test_save_and_load(self):
        correlator = SuccessCorrelator()
        correlator.record_batch(
            [
                TaskOutcome(task_id="1", variant="tldrs", success=True, tokens_used=1000),
                TaskOutcome(task_id="2", variant="tldrs", success=False, tokens_used=2000),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "outcomes.jsonl"
            saved = correlator.save_to_file(path)
            assert saved == 2

            # Load into new correlator
            correlator2 = SuccessCorrelator()
            loaded = correlator2.load_from_file(path)
            assert loaded == 2
            assert len(correlator2._outcomes) == 2
            assert correlator2._outcomes[0].task_id == "1"

    def test_export_for_swe_bench(self):
        correlator = SuccessCorrelator()
        correlator.record_batch(
            [
                TaskOutcome(
                    task_id="django__django-12345",
                    variant="baseline",
                    success=True,
                    tokens_used=10000,
                ),
                TaskOutcome(
                    task_id="django__django-12345",
                    variant="tldrs",
                    success=True,
                    tokens_used=1000,
                    baseline_tokens=10000,
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "swe_bench_results.json"
            result = correlator.export_for_swe_bench(path)
            assert result["exported"] == 2

            with open(path) as f:
                data = json.load(f)
            assert len(data) == 2
            assert data[0]["instance_id"] == "django__django-12345"


class TestCorrelationReport:
    def test_to_dict(self):
        report = CorrelationReport(
            pearson_r=0.5,
            pearson_p=0.01,
            spearman_rho=0.45,
            spearman_p=0.02,
            sample_size=100,
            success_rate_baseline=0.6,
            success_rate_tldrs=0.65,
            success_rate_delta=0.05,
            confidence_interval_95=(-0.02, 0.12),
            variants=[],
            interpretation="Test interpretation.",
        )
        d = report.to_dict()
        assert d["pearson_r"] == 0.5
        assert d["sample_size"] == 100
        assert d["success_rate_delta"] == 0.05

    def test_summary(self):
        report = CorrelationReport(
            pearson_r=0.5,
            pearson_p=0.01,
            spearman_rho=0.45,
            spearman_p=0.02,
            sample_size=100,
            success_rate_baseline=0.6,
            success_rate_tldrs=0.65,
            success_rate_delta=0.05,
            confidence_interval_95=(-0.02, 0.12),
            variants=[],
            interpretation="Test interpretation.",
        )
        summary = report.summary()
        assert "Sample size: 100" in summary
        assert "Baseline: 60.0%" in summary
        assert "TLDRS:    65.0%" in summary
        assert "Pearson r" in summary
