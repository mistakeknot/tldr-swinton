from pathlib import Path
import json
import subprocess


def test_compare_results_track_preset(tmp_path: Path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    baseline = results_dir / "official_datasets_context_baselines.jsonl"
    variant_a = results_dir / "official_datasets_context_symbolkite.jsonl"
    variant_b = results_dir / "official_datasets_context_cassette.jsonl"
    variant_c = results_dir / "official_datasets_context_coveragelens.jsonl"

    baseline.write_text(
        '{"task_id":"t1","context_tokens":10,"total_tokens_total":100}\n',
        encoding="utf-8",
    )
    variant_a.write_text(
        '{"task_id":"t1","context_tokens":5,"total_tokens_total":60}\n',
        encoding="utf-8",
    )
    variant_b.write_text(
        '{"task_id":"t1","context_tokens":6,"total_tokens_total":70}\n',
        encoding="utf-8",
    )
    variant_c.write_text(
        '{"task_id":"t1","context_tokens":7,"total_tokens_total":80}\n',
        encoding="utf-8",
    )

    cmd = [
        "uv",
        "run",
        "python",
        "tldr-bench/scripts/compare_results.py",
        "--track",
        "dataset-context",
        "--results-dir",
        str(results_dir),
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    variants = [row["variant"] for row in data]
    assert str(variant_a) in variants
    assert str(variant_b) in variants
    assert str(variant_c) in variants
