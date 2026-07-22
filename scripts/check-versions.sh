#!/bin/bash
# Thin wrapper — delegates to Sylveste's shared intercheck-versions.sh.
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PLUGIN_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

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
