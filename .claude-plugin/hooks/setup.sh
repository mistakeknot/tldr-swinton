#!/bin/bash
# tldrs Setup Hook
# Runs on: claude --init, claude --init-only, claude --maintenance
# Purpose: Check tldrs install, semantic index, optional features, and emit usage guidance

if command -v tldrs &> /dev/null; then
    # Check semantic index
    if [ ! -d ".tldrs" ]; then
        echo "tldrs: No semantic index. Run 'tldrs index .' to enable semantic search."
    fi
    # Check ast-grep availability
    if ! python3 -c "import ast_grep_py" 2>/dev/null; then
        echo "tldrs: Structural search unavailable. Reinstall with: uv tool install --force tldr-swinton"
    fi
    # Usage guidance — travels with the plugin to any repo
    echo "tldrs: Available. Run 'tldrs diff-context --project . --budget 2000' before reading code. Use 'tldrs context <symbol>' to understand functions/classes. Use 'tldrs find \"query\"' for semantic search."
else
    echo "tldrs: NOT INSTALLED. Install with: pip install tldr-swinton"
    echo "tldrs: Plugin skills will not function until tldrs is installed."
fi
