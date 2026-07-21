#!/bin/bash
# tldrs Setup Hook — health check and quiet cache preparation
# Successful setup emits no context. Reconnaissance is selected on demand by
# the forked tldrs-session-start skill or by direct CLI/MCP calls.

set +e  # Never fail the hook

# `command -v` alone accepts stale entry points whose Python package disappeared.
if ! command -v tldrs &> /dev/null || ! TLDRS_VERSION=$(tldrs --version 2>/dev/null); then
    echo "tldrs: executable is missing or unusable."
    echo "Repair with: curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/install.sh | bash"
    exit 0
fi

# Prebuild quietly. The next selected tldrs call can reuse the cache without
# injecting project structure into every conversation.
if [ -d ".git" ]; then
    tldrs prebuild --project . >/dev/null 2>&1 &
fi
