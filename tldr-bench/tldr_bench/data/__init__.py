from __future__ import annotations

import hashlib
import json
from pathlib import Path


def verify_dataset_manifests(root: str | Path | None = None) -> list[str]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2] / "data"
    if not base.exists():
        return [f"data root not found: {base}"]

    manifest_paths = sorted(base.glob("*/manifest.json"))
    if not manifest_paths:
        return []

    errors: list[str] = []
    for manifest_path in manifest_paths:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest.get("files", [])
        root_dir = manifest_path.parent
        for entry in files:
            name = entry.get("name")
            if not name:
                errors.append(f"{manifest_path}: missing file name")
                continue
            path = root_dir / name
            if not path.exists():
                errors.append(f"{manifest_path}: missing {name}")
                continue
            expected_bytes = entry.get("bytes")
            if isinstance(expected_bytes, int):
                actual_bytes = path.stat().st_size
                if actual_bytes != expected_bytes:
                    errors.append(
                        f"{manifest_path}: size mismatch for {name} "
                        f"(expected {expected_bytes}, got {actual_bytes})"
                    )
            expected_sha = entry.get("sha256")
            if expected_sha:
                actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_sha != expected_sha:
                    errors.append(
                        f"{manifest_path}: sha256 mismatch for {name}"
                    )
    return errors
