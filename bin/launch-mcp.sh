#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Plugin harnesses sometimes launch with a stripped PATH that excludes the
# common user-local install locations for uv. Add the canonical install paths
# before the lookup so installed-but-not-on-PATH uv is found.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}"

if ! command -v uv &>/dev/null; then
    echo "uv not found — install with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    echo "tldr-swinton will work without uv but MCP server unavailable." >&2
    exit 0  # Clean exit — don't trigger retry
fi

exec uv run --directory "$PROJECT_ROOT" --extra mcp-server tldr-mcp "$@"
