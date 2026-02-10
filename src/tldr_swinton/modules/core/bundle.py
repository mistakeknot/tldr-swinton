"""Workspace-scoped precomputed context bundles."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .hybrid_extractor import HybridExtractor


@dataclass
class Bundle:
    commit_sha: str
    branch: str
    created_at: float  # time.time()
    structure: list[dict] = field(default_factory=list)
    # Top-K symbol signatures: [{"id": str, "signature": str, "lines": (int,int)}]
    branch_info: dict = field(default_factory=dict)
    # {"branch": str, "ahead": int, "behind": int, "recent_commits": list[str]}
    metadata: dict = field(default_factory=dict)
    # {"bundle_version": 1, "token_count": int, "file_count": int}
    format_version: int = 1


_DEF_RE = re.compile(
    r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*(?:->\s*([^:]+))?:"
)


def _run_git(project_root: Path, args: list[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root)] + args,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _run_git_int(project_root: Path, args: list[str], default: int = 0) -> int:
    value = _run_git(project_root, args)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _git_ref_exists(project_root: Path, ref: str) -> bool:
    return _run_git(project_root, ["rev-parse", "--verify", ref]) is not None


def _current_head_sha(project_root: Path) -> Optional[str]:
    return _run_git(project_root, ["rev-parse", "HEAD"])


def _current_branch(project_root: Path) -> str:
    branch = _run_git(project_root, ["branch", "--show-current"])
    return branch or "detached"


def _list_tracked_python_files(project_root: Path) -> list[str]:
    output = _run_git(project_root, ["ls-files", "*.py"])
    if output:
        files = [line.strip() for line in output.splitlines() if line.strip()]
        if files:
            return files

    fallback: list[str] = []
    for path in project_root.rglob("*.py"):
        parts = set(path.parts)
        if ".git" in parts or ".tldrs" in parts:
            continue
        fallback.append(path.relative_to(project_root).as_posix())
    return sorted(fallback)


def _extract_symbols_regex(file_path: Path, rel_path: str) -> list[dict]:
    try:
        source = file_path.read_text()
    except OSError:
        return []

    symbols: list[dict] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        match = _DEF_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        symbol_id = f"{rel_path}:{name}"
        symbols.append(
            {
                "id": symbol_id,
                "signature": line.strip(),
                "lines": (lineno, lineno),
            }
        )
    return symbols


def _extract_symbols_from_file(
    extractor: HybridExtractor,
    project_root: Path,
    rel_path: str,
) -> list[dict]:
    file_path = project_root / rel_path
    if not file_path.is_file():
        return []

    try:
        module_info = extractor.extract(str(file_path))
    except Exception:
        return _extract_symbols_regex(file_path, rel_path)

    symbols: list[dict] = []
    seen_ids: set[str] = set()
    for func in module_info.functions:
        raw_name = getattr(func, "name", None)
        if not raw_name:
            continue
        start_line = int(getattr(func, "line_number", 0) or 0)
        end_line = start_line
        signature = func.signature() if hasattr(func, "signature") else f"def {raw_name}(...)"
        symbol_id = f"{rel_path}:{raw_name}"
        if symbol_id in seen_ids:
            suffix = hashlib.sha1(f"{symbol_id}:{start_line}".encode()).hexdigest()[:8]
            symbol_id = f"{symbol_id}@{suffix}"
        seen_ids.add(symbol_id)
        symbols.append(
            {
                "id": symbol_id,
                "signature": signature,
                "lines": (start_line, end_line),
            }
        )

    if symbols:
        return symbols
    return _extract_symbols_regex(file_path, rel_path)


def _collect_branch_info(project_root: Path, branch: str, base_ref: str) -> dict:
    ahead = 0
    behind = 0
    if _git_ref_exists(project_root, base_ref):
        ahead = _run_git_int(project_root, ["rev-list", "--count", f"{base_ref}..HEAD"])
        behind = _run_git_int(project_root, ["rev-list", "--count", f"HEAD..{base_ref}"])

    recent_raw = _run_git(project_root, ["log", "--oneline", "-5"])
    recent_commits = [line for line in (recent_raw or "").splitlines() if line]
    return {
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "recent_commits": recent_commits,
    }


def _bundle_dir(project_root: Path) -> Path:
    return project_root / ".tldrs" / "cache" / "bundles"


def build_bundle(project_root: Path, base_ref: str = "main", top_k: int = 50) -> Bundle:
    project_root = Path(project_root).resolve()
    commit_sha = _current_head_sha(project_root)
    if not commit_sha:
        raise RuntimeError(f"Unable to resolve git HEAD in {project_root}")

    branch = _current_branch(project_root)
    branch_info = _collect_branch_info(project_root, branch=branch, base_ref=base_ref)

    tracked_files = _list_tracked_python_files(project_root)
    extractor = HybridExtractor()
    structure: list[dict] = []
    limit = max(top_k, 0)

    for rel_path in tracked_files:
        file_symbols = _extract_symbols_from_file(extractor, project_root, rel_path)
        structure.extend(file_symbols)
        if len(structure) >= limit:
            break

    if limit:
        structure = structure[:limit]
    else:
        structure = []

    token_count = sum(max(1, len(str(item.get("signature", ""))) // 4) for item in structure)
    metadata = {
        "bundle_version": 1,
        "token_count": token_count,
        "file_count": len(tracked_files),
    }

    return Bundle(
        commit_sha=commit_sha,
        branch=branch,
        created_at=time.time(),
        structure=structure,
        branch_info=branch_info,
        metadata=metadata,
        format_version=1,
    )


def save_bundle(bundle: Bundle, project_root: Path) -> Path:
    project_root = Path(project_root).resolve()
    bundle_dir = _bundle_dir(project_root)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"{bundle.commit_sha}.json"
    bundle_path.write_text(json.dumps(asdict(bundle), indent=2))
    return bundle_path


def load_bundle(project_root: Path) -> Optional[Bundle]:
    project_root = Path(project_root).resolve()
    current_sha = _current_head_sha(project_root)
    if not current_sha:
        return None

    bundle_path = _bundle_dir(project_root) / f"{current_sha}.json"
    if not bundle_path.exists():
        return None

    try:
        raw = json.loads(bundle_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    normalized_structure: list[dict] = []
    for item in raw.get("structure", []):
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        lines = normalized.get("lines")
        if isinstance(lines, list) and len(lines) == 2:
            try:
                normalized["lines"] = (int(lines[0]), int(lines[1]))
            except (TypeError, ValueError):
                normalized["lines"] = None
        normalized_structure.append(normalized)

    try:
        created_at = float(raw.get("created_at", 0.0))
    except (TypeError, ValueError):
        created_at = 0.0

    return Bundle(
        commit_sha=str(raw.get("commit_sha", current_sha)),
        branch=str(raw.get("branch", "")),
        created_at=created_at,
        structure=normalized_structure,
        branch_info=dict(raw.get("branch_info", {})),
        metadata=dict(raw.get("metadata", {})),
        format_version=int(raw.get("format_version", 1)),
    )


def is_bundle_stale(bundle: Bundle, project_root: Path) -> bool:
    project_root = Path(project_root).resolve()
    current_sha = _current_head_sha(project_root)
    if not current_sha or bundle.commit_sha != current_sha:
        return True

    for rel_path in _list_tracked_python_files(project_root):
        file_path = project_root / rel_path
        try:
            if file_path.stat().st_mtime > bundle.created_at:
                return True
        except OSError:
            return True

    return False


def cleanup_old_bundles(project_root: Path, keep: int = 5) -> int:
    project_root = Path(project_root).resolve()
    bundle_dir = _bundle_dir(project_root)
    if not bundle_dir.exists():
        return 0

    keep_count = max(keep, 0)
    bundle_files = sorted(
        [path for path in bundle_dir.glob("*.json") if path.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    stale_files = bundle_files[keep_count:]

    deleted = 0
    for file_path in stale_files:
        try:
            file_path.unlink()
            deleted += 1
        except OSError:
            continue
    return deleted


def bundle_to_context_pack_dict(bundle: Bundle) -> dict:
    slices = [
        {
            "id": item.get("id"),
            "signature": item.get("signature", ""),
            "code": None,
            "lines": item.get("lines"),
            "relevance": "precomputed",
        }
        for item in bundle.structure
    ]
    return {
        "slices": slices,
        "budget_used": 0,
        "unchanged": None,
        "cache_stats": {"source": "bundle", "commit": bundle.commit_sha},
    }
