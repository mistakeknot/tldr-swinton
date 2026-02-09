#!/bin/bash
#
# Bump version across all three locations, commit, push, and reinstall.
#
# Usage:
#   scripts/bump-version.sh 0.7.0
#   scripts/bump-version.sh 0.7.0 --dry-run
#
# This replaces the manual 5-step runbook in CLAUDE.md with one command.
# Files updated:
#   1. pyproject.toml           (this repo)
#   2. .claude-plugin/plugin.json (this repo)
#   3. ../interagency-marketplace/.claude-plugin/marketplace.json (sibling repo)

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
MARKETPLACE_ROOT="$REPO_ROOT/../interagency-marketplace"
DRY_RUN=false

if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; NC=''
fi

usage() {
    echo "Usage: $0 <version> [--dry-run]"
    echo "  version   Semver string, e.g. 0.7.0"
    echo "  --dry-run Show what would change without writing"
    exit 1
}

# --- Parse args ---
VERSION=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h) usage ;;
        *) VERSION="$arg" ;;
    esac
done

[ -z "$VERSION" ] && usage

# Validate semver-ish format
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'; then
    echo -e "${RED}Error: '$VERSION' doesn't look like a valid version (expected X.Y.Z)${NC}" >&2
    exit 1
fi

# --- Read current version ---
CURRENT=$(grep -E '^version\s*=' "$REPO_ROOT/pyproject.toml" | sed 's/.*"\([^"]*\)".*/\1/')
echo "Current version: $CURRENT"
echo "New version:     $VERSION"

if [ "$CURRENT" = "$VERSION" ]; then
    echo -e "${YELLOW}Already at $VERSION — nothing to do.${NC}"
    exit 0
fi

# --- Check marketplace repo exists ---
if [ ! -f "$MARKETPLACE_ROOT/.claude-plugin/marketplace.json" ]; then
    echo -e "${RED}Error: Marketplace repo not found at $MARKETPLACE_ROOT${NC}" >&2
    echo "Expected sibling directory: ../interagency-marketplace" >&2
    exit 1
fi

# --- Update files ---
echo ""

update_file() {
    local file="$1" pattern="$2" replacement="$3" label="$4"
    if $DRY_RUN; then
        echo -e "  ${YELLOW}[dry-run]${NC} $label"
    else
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|$pattern|$replacement|" "$file"
        else
            sed -i "s|$pattern|$replacement|" "$file"
        fi
        echo -e "  ${GREEN}Updated${NC} $label"
    fi
}

update_file \
    "$REPO_ROOT/pyproject.toml" \
    "^version = \"$CURRENT\"" \
    "version = \"$VERSION\"" \
    "pyproject.toml"

update_file \
    "$REPO_ROOT/.claude-plugin/plugin.json" \
    "\"version\": \"$CURRENT\"" \
    "\"version\": \"$VERSION\"" \
    ".claude-plugin/plugin.json"

update_file \
    "$MARKETPLACE_ROOT/.claude-plugin/marketplace.json" \
    "\"version\": \"$CURRENT\"" \
    "\"version\": \"$VERSION\"" \
    "interagency-marketplace/marketplace.json"

if $DRY_RUN; then
    echo -e "\n${YELLOW}Dry run complete. No files changed.${NC}"
    exit 0
fi

# --- Commit and push tldr-swinton ---
echo ""
cd "$REPO_ROOT"
git add pyproject.toml .claude-plugin/plugin.json
git commit -m "chore: bump version to $VERSION"
git push
echo -e "${GREEN}Pushed tldr-swinton${NC}"

# --- Commit and push marketplace ---
cd "$MARKETPLACE_ROOT"
git add .claude-plugin/marketplace.json
git commit -m "chore: bump tldr-swinton to v$VERSION"
git push
echo -e "${GREEN}Pushed interagency-marketplace${NC}"

# --- Reinstall CLI ---
cd "$REPO_ROOT"
uv tool install --force . 2>&1 | tail -3
echo ""

# --- Verify ---
INSTALLED=$(tldrs --version 2>&1)
echo -e "${GREEN}Done!${NC} tldrs $INSTALLED"
echo ""
echo "Next: restart Claude Code sessions to pick up the new plugin version."
