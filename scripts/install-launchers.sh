#!/usr/bin/env bash

set -euo pipefail

INSTALL_DIR=${1:?Usage: install-launchers.sh INSTALL_DIR [BIN_DIR]}
BIN_DIR=${2:-"${HOME}/.local/bin"}

if [ ! -d "$INSTALL_DIR/.venv/bin" ]; then
    echo "tldr-swinton: missing virtual environment at $INSTALL_DIR/.venv" >&2
    exit 1
fi

INSTALL_DIR=$(cd "$INSTALL_DIR" && pwd -P)
mkdir -p "$BIN_DIR"

for command in tldrs tldr-swinton tldr-mcp; do
    target="$INSTALL_DIR/.venv/bin/$command"
    launcher="$BIN_DIR/$command"
    temporary="$launcher.tmp.$$"

    if [ ! -x "$target" ]; then
        echo "tldr-swinton: missing entry point $target" >&2
        exit 1
    fi

    escaped_target=$(printf '%q' "$target")
    {
        printf '#!/usr/bin/env bash\n'
        printf 'exec %s "$@"\n' "$escaped_target"
    } > "$temporary"
    chmod 0755 "$temporary"
    mv -f "$temporary" "$launcher"
done

echo "Installed tldr-swinton launchers in $BIN_DIR"
