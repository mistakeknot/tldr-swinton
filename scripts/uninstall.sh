#!/usr/bin/env bash
#
# tldr-swinton uninstaller
# Usage: curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/uninstall.sh | bash
#
# Options:
#   --yes           Skip confirmation prompts
#   --keep-indexes  Don't remove .tldrs/ directories from projects
#   --dir PATH      Installation directory (default: ~/tldr-swinton)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
INSTALL_DIR="${HOME}/tldr-swinton"
SKIP_CONFIRM=false
KEEP_INDEXES=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --yes|-y)
            SKIP_CONFIRM=true
            shift
            ;;
        --keep-indexes)
            KEEP_INDEXES=true
            shift
            ;;
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "tldr-swinton uninstaller"
            echo ""
            echo "Usage: uninstall.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --yes, -y       Skip confirmation prompts"
            echo "  --keep-indexes  Don't offer to remove .tldrs/ directories"
            echo "  --dir PATH      Installation directory (default: ~/tldr-swinton)"
            echo "  --help, -h      Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           tldr-swinton Uninstaller                             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Confirmation
if [ "$SKIP_CONFIRM" = false ]; then
    echo -e "This will uninstall tldr-swinton from: ${YELLOW}${INSTALL_DIR}${NC}"
    echo ""
    read -p "Continue? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Step 1: Remove shell alias
echo ""
echo -e "${BLUE}[1/3]${NC} Removing shell alias..."

SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

if [ -n "$SHELL_RC" ]; then
    if grep -q "alias tldrs=" "$SHELL_RC" 2>/dev/null; then
        # Remove the tldr-swinton section
        sed -i.bak '/# tldr-swinton/d' "$SHELL_RC"
        sed -i.bak '/alias tldrs=/d' "$SHELL_RC"
        rm -f "${SHELL_RC}.bak"
        echo -e "  ${GREEN}✓${NC} Removed alias from ${SHELL_RC}"
    else
        echo -e "  ${YELLOW}→${NC} No alias found in ${SHELL_RC}"
    fi
else
    echo -e "  ${YELLOW}→${NC} No shell rc file found"
fi

# Step 2: Remove pip package if installed globally
echo ""
echo -e "${BLUE}[2/3]${NC} Checking for pip installations..."

# Check various Python installations
for PYTHON in python3 python3.11 python3.12 python3.10; do
    if command -v "$PYTHON" &>/dev/null; then
        if "$PYTHON" -m pip list 2>/dev/null | grep -q "tldr-swinton"; then
            echo -e "  ${YELLOW}→${NC} Removing tldr-swinton from $PYTHON..."
            "$PYTHON" -m pip uninstall -y tldr-swinton 2>/dev/null || true
            echo -e "  ${GREEN}✓${NC} Removed from $PYTHON"
        fi
    fi
done

# Also check homebrew Python specifically
if [ -x "/opt/homebrew/opt/python@3.11/bin/python3.11" ]; then
    if /opt/homebrew/opt/python@3.11/bin/python3.11 -m pip list 2>/dev/null | grep -q "tldr-swinton"; then
        echo -e "  ${YELLOW}→${NC} Removing tldr-swinton from homebrew Python..."
        /opt/homebrew/opt/python@3.11/bin/python3.11 -m pip uninstall -y tldr-swinton 2>/dev/null || true
        echo -e "  ${GREEN}✓${NC} Removed from homebrew Python"
    fi
fi

echo -e "  ${GREEN}✓${NC} Pip cleanup complete"

# Step 3: Remove installation directory
echo ""
echo -e "${BLUE}[3/3]${NC} Removing installation directory..."

if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "  ${GREEN}✓${NC} Removed ${INSTALL_DIR}"
else
    echo -e "  ${YELLOW}→${NC} Directory not found: ${INSTALL_DIR}"
fi

# Optional: Remove .tldr indexes from projects
if [ "$KEEP_INDEXES" = false ] && [ "$SKIP_CONFIRM" = false ]; then
    echo ""
    echo -e "${YELLOW}Note:${NC} Project indexes (.tldrs/ directories) were not removed."
    echo -e "To remove an index from a project, run: ${BLUE}rm -rf /path/to/project/.tldrs${NC}"
fi

# Success message
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                   Uninstall Complete!                          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Restart your shell or run: ${BLUE}source ${SHELL_RC}${NC}"
echo ""
