#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
DATA_DIR="$ROOT_DIR/tldr-bench/data"

if ! command -v git-lfs >/dev/null 2>&1; then
  echo "git-lfs not found. Install git-lfs first." >&2
  exit 1
fi

if [ ! -d "$DATA_DIR/.git" ]; then
  echo "Dataset submodule not initialized at $DATA_DIR" >&2
  echo "Run: git submodule update --init --recursive" >&2
  exit 1
fi

echo "Configuring Git LFS in dataset submodule..."
if ! git -C "$DATA_DIR" lfs install; then
  echo "git lfs install failed (hooks conflict)." >&2
  echo "Run: git lfs update --manual and merge hooks, then re-run." >&2
  exit 1
fi

ATTRS="$DATA_DIR/.gitattributes"
if [ ! -f "$ATTRS" ]; then
  echo ".gitattributes not found at $ATTRS" >&2
  exit 1
fi

if ! rg -q "data/" "$ATTRS"; then
  echo "Expected LFS patterns missing from $ATTRS" >&2
  exit 1
fi

echo "OK"
