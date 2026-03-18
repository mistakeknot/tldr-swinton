#!/usr/bin/env bash
set -euo pipefail
# tldr-swinton/interlab.sh — wraps pytest suite for interlab.
# Primary: test_pass_rate (pytest results)
# NOTE: token_efficiency_eval.py requires `tldrs` binary — skip for now.

MONOREPO="$(cd "$(dirname "$0")/../.." && pwd)"
HARNESS="${INTERLAB_HARNESS:-$MONOREPO/interverse/interlab/scripts/py-bench-harness.sh}"
DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -f "$HARNESS" ]]; then
    echo "METRIC test_pass_rate=-1"
    echo "METRIC error=1"
    exit 0
fi

bash "$HARNESS" --cmd "uv run pytest tests/ -q --tb=no" --metric test_pass_rate --dir "$DIR" --mode pytest
