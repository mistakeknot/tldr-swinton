#!/bin/bash
# tldrs Setup Hook
# Runs on: claude --init, claude --init-only, claude --maintenance
# Purpose: Check tldrs install, semantic index, and optional features

if command -v tldrs &> /dev/null; then
    # Check semantic index
    if [ ! -d ".tldrs" ]; then
        echo "tldrs: No semantic index. Run 'tldrs index .' to enable semantic search."
    fi
    # Check ast-grep availability
    if ! python3 -c "import ast_grep_py" 2>/dev/null; then
        echo "tldrs: Structural search unavailable. Reinstall with: uv tool install --force tldr-swinton"
    fi
else
    echo "tldrs: NOT INSTALLED. Install with: pip install tldr-swinton"
    echo "tldrs: Plugin skills will not function until tldrs is installed."
fi
