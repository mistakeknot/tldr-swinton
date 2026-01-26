#!/bin/bash
#
# Verify all version locations are in sync
# Called by pre-commit hook and can be run manually
#
# Locations checked:
#   - pyproject.toml: version = "X.Y.Z"
#   - .claude-plugin/plugin.json: "version": "X.Y.Z"

set -e

# Colors for output (disabled if not a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    NC=''
fi

# Find repo root
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Extract versions
PYPROJECT_VERSION=$(grep -E '^version\s*=' pyproject.toml | sed 's/.*"\([^"]*\)".*/\1/')
PLUGIN_VERSION=$(grep -E '"version"' .claude-plugin/plugin.json | sed 's/.*"\([0-9][^"]*\)".*/\1/')

# Check if we could extract both
if [ -z "$PYPROJECT_VERSION" ]; then
    echo -e "${RED}Error: Could not extract version from pyproject.toml${NC}" >&2
    exit 1
fi

if [ -z "$PLUGIN_VERSION" ]; then
    echo -e "${RED}Error: Could not extract version from .claude-plugin/plugin.json${NC}" >&2
    exit 1
fi

# Compare
if [ "$PYPROJECT_VERSION" != "$PLUGIN_VERSION" ]; then
    echo -e "${RED}Version mismatch detected!${NC}" >&2
    echo "" >&2
    echo "  pyproject.toml:              $PYPROJECT_VERSION" >&2
    echo "  .claude-plugin/plugin.json:  $PLUGIN_VERSION" >&2
    echo "" >&2
    echo "All versions must match. Update both files before committing." >&2
    echo "See CLAUDE.md 'Plugin Publishing Runbook' for the full process." >&2
    exit 1
fi

# Success
if [ "${1:-}" = "--verbose" ] || [ "${1:-}" = "-v" ]; then
    echo -e "${GREEN}✓ Versions in sync: $PYPROJECT_VERSION${NC}"
fi

exit 0
