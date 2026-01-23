#!/bin/bash
# tldrs Setup Hook
# Runs on: claude --init, claude --init-only, claude --maintenance
# Purpose: Check if semantic index exists and suggest building it

# Only show message if tldrs is installed but no index exists
if command -v tldrs &> /dev/null; then
    if [ ! -d ".tldrs" ]; then
        echo "tldrs: No semantic index found in this project."
        echo "  Run: tldrs index ."
        echo "  This enables semantic search with: tldrs find \"your query\""
    fi
fi
