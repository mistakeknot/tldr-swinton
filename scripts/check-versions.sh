#!/bin/bash
# Thin wrapper — delegates to Sylveste's shared intercheck-versions.sh.
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PLUGIN_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

# Match Intercore's canonical publisher target before the shared checker's
# legacy sibling-layout fallback. Callers may override this explicitly.
if [ -z "${INTERCHECK_MARKETPLACE_JSON:-}" ]; then
    REGISTERED_MARKETPLACE="${HOME}/.claude/plugins/marketplaces/interagency-marketplace/.claude-plugin/marketplace.json"
    if [ -f "$REGISTERED_MARKETPLACE" ]; then
        export INTERCHECK_MARKETPLACE_JSON="$REGISTERED_MARKETPLACE"
    fi
fi

if [ -n "${TLDRS_INTERCHECK_VERSIONS:-}" ]; then
    CANDIDATES=("$TLDRS_INTERCHECK_VERSIONS")
else
    CANDIDATES=(
        "$PLUGIN_ROOT/../Sylveste/scripts/intercheck-versions.sh"
        "$SCRIPT_DIR/../../../scripts/intercheck-versions.sh"
    )
fi

for candidate in "${CANDIDATES[@]}"; do
    if [ -x "$candidate" ]; then
        exec "$candidate" "$@"
    fi
done

{
    echo "Error: executable intercheck-versions.sh not found; checked:"
    printf '  - %s\n' "${CANDIDATES[@]}"
} >&2
exit 1
