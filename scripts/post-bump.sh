#!/bin/bash
#
# tldr-swinton post-bump hook — called by interbump before git commit.
# Reinstalls CLI tool and checks interbench eval coverage.
#
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# Reinstall CLI so `tldrs --version` matches
cd "$REPO_ROOT"
uv tool install --force . 2>&1 | tail -3

# Non-blocking interbench sync check
INTERBENCH_CHECK="/root/projects/Interverse/infra/interbench/scripts/check_tldrs_sync.py"
if command -v tldrs &>/dev/null && [ -f "$INTERBENCH_CHECK" ]; then
    echo ""
    if ! tldrs manifest | python3 "$INTERBENCH_CHECK" --quiet 2>/dev/null; then
        echo -e "\033[0;33mWarning: interbench eval coverage has gaps. Run /tldrs-interbench-sync to fix.\033[0m"
    fi
fi
