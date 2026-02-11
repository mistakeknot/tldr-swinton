#!/bin/bash
# tldrs PostToolUse hook for Read — auto-inject extract on large files
# Fires AFTER Read completes. Runs tldrs extract and returns as additionalContext.
# Only fires for code files >300 lines. Per-file flagging prevents duplicates.
#
# Input: JSON on stdin with { session_id, tool_name, tool_input: { file_path } }

set +e  # Never fail the hook

# Read stdin (hook input is JSON)
INPUT=$(cat 2>/dev/null) || exit 0

# Extract file path
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || exit 0
[ -z "$FILE" ] && exit 0

# Skip non-existent files
[ -f "$FILE" ] || exit 0

# Skip non-code files
case "$FILE" in
    *.md|*.txt|*.json|*.yaml|*.yml|*.toml|*.cfg|*.ini|*.env|*.lock|*.csv|*.html|*.css|*.svg|*.png|*.jpg|*.gif|*.ico|*.pdf|*.xml|*.sql|*.log|*.sh)
        exit 0
        ;;
esac

# Skip files under 300 lines
LINE_COUNT=$(wc -l < "$FILE" 2>/dev/null || echo 0)
LINE_COUNT=$(echo "$LINE_COUNT" | tr -d ' ')
if [ "$LINE_COUNT" -lt 300 ]; then
    exit 0
fi

# Check tldrs is installed
command -v tldrs &> /dev/null || exit 0

# Per-file flag: only extract once per file per session
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null) || exit 0
if [ -n "$SESSION_ID" ]; then
    FILE_HASH=$(echo -n "$FILE" | md5sum | cut -d' ' -f1)
    FLAG="/tmp/tldrs-extract-${SESSION_ID}-${FILE_HASH}"
    [ -f "$FLAG" ] && exit 0
fi

# Run extract with timeout
EXTRACT_OUTPUT=$(timeout 5 tldrs extract "$FILE" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$EXTRACT_OUTPUT" ]; then
    exit 0
fi

# Create per-file flag so we don't re-extract this file
if [ -n "$SESSION_ID" ] && [ -n "$FILE_HASH" ]; then
    touch "$FLAG" 2>/dev/null
fi

# Return as additionalContext JSON — use python for safe JSON encoding
echo "$EXTRACT_OUTPUT" | python3 -c "
import sys, json
extract = sys.stdin.read()
file_path = sys.argv[1]
line_count = sys.argv[2]
msg = f'tldrs extract output for {file_path} ({line_count} lines):\n{extract}'
print(json.dumps({'additionalContext': msg}))
" "$FILE" "$LINE_COUNT" 2>/dev/null || exit 0
