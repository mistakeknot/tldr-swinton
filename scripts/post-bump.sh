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

# Kimi has its own manifest outside Intercore's standard version surfaces.
# Keep its release metadata synchronized in the same atomic bump transaction.
KIMI_MANIFEST="$REPO_ROOT/kimi.plugin.json"
CLAUDE_MANIFEST="$REPO_ROOT/.claude-plugin/plugin.json"
if [[ -f "$KIMI_MANIFEST" && -f "$CLAUDE_MANIFEST" ]]; then
    python3 - "$KIMI_MANIFEST" "$CLAUDE_MANIFEST" "$TARGET_VERSION" <<'PY'
import json
import os
from pathlib import Path
import sys
import tempfile

kimi_path = Path(sys.argv[1])
claude = json.loads(Path(sys.argv[2]).read_text())
kimi = json.loads(kimi_path.read_text())
kimi["version"] = sys.argv[3]
if claude.get("description"):
    kimi["description"] = claude["description"]
author = claude.get("author")
if isinstance(author, dict):
    author = author.get("name")
if author:
    kimi["author"] = author
interface = kimi.setdefault("interface", {})
interface.setdefault("displayName", kimi.get("name", "tldr-swinton"))
description = kimi.get("description", "")
interface["shortDescription"] = (
    description if len(description) <= 120 else description[:117].rstrip() + "..."
)
fd, temporary = tempfile.mkstemp(prefix=".kimi-plugin-", dir=kimi_path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(kimi, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temporary, kimi_path)
except BaseException:
    try:
        os.unlink(temporary)
    except OSError:
        pass
    raise
PY
fi

uv tool install --force . 2>&1 | tail -3

# Non-blocking interbench sync check
INTERBENCH_CHECK="/root/projects/Interverse/infra/interbench/scripts/check_tldrs_sync.py"
if command -v tldrs &>/dev/null && [ -f "$INTERBENCH_CHECK" ]; then
    echo ""
    if ! tldrs manifest | python3 "$INTERBENCH_CHECK" --quiet 2>/dev/null; then
        echo -e "\033[0;33mWarning: interbench eval coverage has gaps. Run /tldrs-interbench-sync to fix.\033[0m"
    fi
fi
