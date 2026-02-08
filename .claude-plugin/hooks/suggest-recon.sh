#!/bin/bash
# tldrs PreToolUse hook for Read — nudge agent to use tldrs first
# Must be fast: only checks a flag file, never runs tldrs itself
#
# Input: JSON on stdin with { session_id, tool_name, tool_input: { file_path } }

# Read stdin once (hook input is JSON)
INPUT=$(cat)

# Extract session_id for stable flag file (persists across hook calls in one conversation)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
if [ -z "$SESSION_ID" ]; then
    exit 0
fi
FLAG="/tmp/tldrs-session-${SESSION_ID}"

# If tldrs has already been used this session, stay silent
[ -f "$FLAG" ] && exit 0

# Check if tldrs is installed
command -v tldrs &> /dev/null || exit 0

# Extract the file path from tool_input
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# Skip non-code files — no need to nudge for docs, configs, etc.
case "$FILE" in
    *.md|*.txt|*.json|*.yaml|*.yml|*.toml|*.cfg|*.ini|*.env|*.lock|*.csv|*.html|*.css|*.svg|*.png|*.jpg|*.gif|*.ico|*.pdf)
        exit 0
        ;;
esac

# Skip if file is very short (< 50 lines) — not worth tldrs overhead
if [ -f "$FILE" ] && [ "$(wc -l < "$FILE" 2>/dev/null || echo 999)" -lt 50 ]; then
    exit 0
fi

# Nudge the agent
echo "tip: Run 'tldrs diff-context --project . --budget 2000' before reading code files to save 48-73% tokens."
echo "tip: Or use 'tldrs context <symbol> --project . --depth 2' to understand a specific function."

# Create the flag so we only nudge once per session
touch "$FLAG"
