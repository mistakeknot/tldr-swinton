#!/bin/bash
#
# tldr-swinton post-bump hook — called before Intercore writes version files.
# Applies the requested package version, reinstalls the CLI tool, and checks
# interbench eval coverage. Intercore then writes/verifies all version surfaces.
#
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TARGET_VERSION="${1:?target version is required}"

# Intercore invokes this legacy hook before its bump phase, so update package
# metadata first or uv will reinstall the prior release.
cd "$REPO_ROOT"
uv version "$TARGET_VERSION" --no-sync
uv tool install --force . 2>&1 | tail -3

# Non-blocking interbench sync check
INTERBENCH_CHECK="/root/projects/Interverse/infra/interbench/scripts/check_tldrs_sync.py"
if command -v tldrs &>/dev/null && [ -f "$INTERBENCH_CHECK" ]; then
    echo ""
    if ! tldrs manifest | python3 "$INTERBENCH_CHECK" --quiet 2>/dev/null; then
        echo -e "\033[0;33mWarning: interbench eval coverage has gaps. Run /tldrs-interbench-sync to fix.\033[0m"
    fi
fi
