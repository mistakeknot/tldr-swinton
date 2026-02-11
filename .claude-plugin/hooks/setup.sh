#!/bin/bash
# tldrs Setup Hook — Dynamic Briefing
# Runs at session start. Auto-runs diff-context and injects output.
# Fallback chain: diff-context → structure → static tip
# Must complete within 10s (Claude Code setup hook timeout).

set +e  # Never fail the hook

# Check tldrs is installed
if ! command -v tldrs &> /dev/null; then
    echo "tldrs: NOT INSTALLED. Install with: pip install tldr-swinton"
    echo "tldrs: Plugin skills will not function until tldrs is installed."
    exit 0
fi

# Check ast-grep availability (non-blocking warning)
if ! python3 -c "import ast_grep_py" 2>/dev/null; then
    echo "tldrs: Structural search unavailable. Reinstall with: uv tool install --force tldr-swinton"
fi

# Prebuild cache in background (fast, <1s)
if [ -d ".git" ]; then
    tldrs prebuild --project . >/dev/null 2>&1 &
fi

# Count project files
PY_COUNT=$(find . -name '*.py' -not -path './.tldrs/*' -not -path './.git/*' -not -path './.venv/*' -not -path './venv/*' -not -path './.env/*' -not -path '*/__pycache__/*' -not -path './node_modules/*' -not -path './.uv-cache/*' 2>/dev/null | wc -l | tr -d ' ')

# Check semantic index
INDEX_STATUS="not built"
if [ -d ".tldrs" ]; then
    INDEX_STATUS="ready"
fi

# Determine if there are recent changes
CHANGED_COUNT=0
CHANGED_FILES=""
if [ -d ".git" ]; then
    DIFF_STAT=$(git diff --stat HEAD 2>/dev/null)
    if [ -n "$DIFF_STAT" ]; then
        CHANGED_COUNT=$(git diff --name-only HEAD 2>/dev/null | wc -l | tr -d ' ')
        CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null | head -10 | tr '\n' ', ' | sed 's/,$//')
    fi
fi

# --- Attempt to run tldrs diff-context or structure ---
TLDRS_OUTPUT=""
if [ "$CHANGED_COUNT" -gt 0 ]; then
    # Has changes — run diff-context with timeout
    TLDRS_OUTPUT=$(timeout 7 tldrs diff-context --project . --preset compact 2>/dev/null)
    if [ $? -ne 0 ] || [ -z "$TLDRS_OUTPUT" ]; then
        # diff-context failed or timed out — try structure
        TLDRS_OUTPUT=$(timeout 3 tldrs structure src/ 2>/dev/null || true)
    fi
else
    # Clean tree — run structure
    TLDRS_OUTPUT=$(timeout 5 tldrs structure src/ 2>/dev/null || true)
fi

# --- Format output ---
echo "Project: $(basename "$(pwd)") (${PY_COUNT} Python files, ${CHANGED_COUNT} changed since last commit)"
echo "Semantic index: ${INDEX_STATUS}"

if [ -n "$CHANGED_FILES" ]; then
    echo "Changed files: ${CHANGED_FILES}"
fi

echo ""

if [ -n "$TLDRS_OUTPUT" ]; then
    echo "$TLDRS_OUTPUT"
else
    # Final fallback — static tip
    echo "Run 'tldrs diff-context --project . --preset compact' before reading code."
    echo "Use 'tldrs extract <file>' for file structure."
fi

echo ""
echo "Available presets: compact, minimal, multi-turn"
