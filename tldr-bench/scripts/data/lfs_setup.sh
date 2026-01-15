#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

if ! command -v git-lfs >/dev/null 2>&1; then
  echo "git-lfs not found. Install git-lfs first." >&2
  exit 1
fi

echo "Configuring Git LFS..."
if ! git -C "$ROOT_DIR" lfs install; then
  echo "git lfs install failed (hooks conflict)." >&2
  echo "Run: git lfs update --manual and merge hooks, then re-run." >&2
  exit 1
fi

ATTRS="$ROOT_DIR/.gitattributes"
if [ ! -f "$ATTRS" ]; then
  echo ".gitattributes not found at $ATTRS" >&2
  exit 1
fi

if ! rg -q "tldr-bench/data" "$ATTRS"; then
  echo "Expected LFS patterns missing from $ATTRS" >&2
  exit 1
fi

echo "OK"
