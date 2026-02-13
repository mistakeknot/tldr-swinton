#!/bin/bash
# tldrs PreToolUse hook for Serena editing — auto-inject caller analysis
# Fires BEFORE replace_symbol_body or rename_symbol to show callers.
# Prevents breaking callers during refactoring operations.
#
# Input: JSON on stdin with { session_id, tool_name, tool_input: { name_path, relative_path } }
# Output: JSON with additionalContext showing callers

set +e  # Never fail the hook

# Read stdin (hook input is JSON)
INPUT=$(cat 2>/dev/null) || exit 0

# Extract symbol info from tool input
NAME_PATH=$(echo "$INPUT" | jq -r '.tool_input.name_path // ""' 2>/dev/null) || exit 0
[ -z "$NAME_PATH" ] && exit 0

# Extract the leaf symbol name (last segment of the name path)
# e.g. "MyClass/my_method" → "my_method", "my_function" → "my_function"
SYMBOL=$(echo "$NAME_PATH" | sed 's|.*/||')
[ -z "$SYMBOL" ] && exit 0

# Strip any overload index (e.g. "my_method[0]" → "my_method")
SYMBOL=$(echo "$SYMBOL" | sed 's/\[.*\]$//')

# Check tldrs is installed
command -v tldrs &> /dev/null || exit 0

# Check project has tldrs data (needs call graph)
[ -d ".git" ] || exit 0

# Per-symbol flag: only analyze once per symbol per session
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null) || exit 0
if [ -n "$SESSION_ID" ]; then
    SYM_HASH=$(echo -n "$SYMBOL" | md5sum | cut -d' ' -f1)
    FLAG="/tmp/tldrs-impact-${SESSION_ID}-${SYM_HASH}"
    [ -f "$FLAG" ] && exit 0
fi

# Run impact analysis with timeout (must be fast — PreToolUse blocks the edit)
IMPACT_OUTPUT=$(timeout 5 tldrs impact "$SYMBOL" --depth 2 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$IMPACT_OUTPUT" ]; then
    exit 0
fi

# Create per-symbol flag
if [ -n "$SESSION_ID" ] && [ -n "$SYM_HASH" ]; then
    touch "$FLAG" 2>/dev/null
fi

# Extract tool name for context message
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "edit"' 2>/dev/null)
TOOL_SHORT=$(echo "$TOOL_NAME" | sed 's/.*__//')

# Return as additionalContext JSON
echo "$IMPACT_OUTPUT" | python3 -c "
import sys, json
impact = sys.stdin.read()
symbol = sys.argv[1]
tool = sys.argv[2]
name_path = sys.argv[3]
msg = f'tldrs caller analysis for {name_path} (before {tool}):\n{impact}\n\nReview callers above before proceeding. Update callers if the change breaks their assumptions.'
print(json.dumps({'additionalContext': msg}))
" "$SYMBOL" "$TOOL_SHORT" "$NAME_PATH" 2>/dev/null || exit 0
