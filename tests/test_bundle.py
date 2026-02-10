from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from tldr_swinton.modules.core.bundle import (
    Bundle,
    build_bundle,
    bundle_to_context_pack_dict,
    cleanup_old_bundles,
    is_bundle_stale,
    load_bundle,
    save_bundle,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "tests@example.com")
    _git(tmp_path, "config", "user.name", "Tests")
    (tmp_path / "app.py").write_text(
        "def alpha(x):\n"
        "    return x + 1\n\n"
        "def beta(y):\n"
        "    return alpha(y)\n"
    )
    (tmp_path / "helpers.py").write_text(
        "def helper(value):\n"
        "    return value * 2\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def test_build_bundle_basic(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    bundle = build_bundle(repo, top_k=10)

    assert len(bundle.commit_sha) == 40
    assert bundle.branch
    assert bundle.created_at > 0
    assert 0 < len(bundle.structure) <= 10
    assert bundle.branch_info["branch"] == bundle.branch
    assert isinstance(bundle.branch_info["recent_commits"], list)
    assert bundle.metadata["bundle_version"] == 1
    assert bundle.metadata["file_count"] == 2
    assert "token_count" in bundle.metadata


def test_save_and_load_bundle(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    bundle = build_bundle(repo)
    bundle_path = save_bundle(bundle, repo)
    loaded = load_bundle(repo)

    assert bundle_path.exists()
    assert loaded is not None
    assert loaded.commit_sha == bundle.commit_sha
    assert loaded.branch == bundle.branch
    assert loaded.metadata == bundle.metadata
    assert loaded.structure == bundle.structure


def test_load_bundle_missing(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    assert load_bundle(repo) is None


def test_is_bundle_stale_same_sha(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    bundle = build_bundle(repo)
    assert is_bundle_stale(bundle, repo) is False


def test_is_bundle_stale_new_commit(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    bundle = build_bundle(repo)

    app_file = repo / "app.py"
    app_file.write_text(
        "def alpha(x):\n"
        "    return x + 2\n\n"
        "def beta(y):\n"
        "    return alpha(y)\n"
    )
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "change alpha")

    assert is_bundle_stale(bundle, repo) is True


def test_cleanup_old_bundles(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    bundle_dir = repo / ".tldrs" / "cache" / "bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(5):
        path = bundle_dir / f"dummy-{idx}.json"
        path.write_text("{}")
        stamp = time.time() - (idx * 10)
        os.utime(path, (stamp, stamp))

    deleted = cleanup_old_bundles(repo, keep=2)
    remaining = sorted(bundle_dir.glob("*.json"))

    assert deleted == 3
    assert len(remaining) == 2


def test_bundle_to_context_pack_dict() -> None:
    bundle = Bundle(
        commit_sha="abc123",
        branch="main",
        created_at=time.time(),
        structure=[{"id": "app.py:alpha", "signature": "def alpha(x):", "lines": (1, 2)}],
    )

    result = bundle_to_context_pack_dict(bundle)

    assert "slices" in result
    assert result["budget_used"] == 0
    assert result["unchanged"] is None
    assert result["cache_stats"]["source"] == "bundle"
    assert result["cache_stats"]["commit"] == "abc123"
    assert result["slices"][0]["id"] == "app.py:alpha"
    assert result["slices"][0]["relevance"] == "precomputed"
    assert result["slices"][0]["code"] is None
