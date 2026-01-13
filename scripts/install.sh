#!/usr/bin/env bash
#
# tldr-swinton installer
# One-liner: curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/install.sh | bash
#
# Options:
#   --yes           Skip confirmation prompts
#   --no-ollama     Skip Ollama model setup
#   --model NAME    Ollama embedding model (default: nomic-embed-text)
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
SKIP_OLLAMA=false
OLLAMA_MODEL="nomic-embed-text"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --yes|-y)
            SKIP_CONFIRM=true
            shift
            ;;
        --no-ollama)
            SKIP_OLLAMA=true
            shift
            ;;
        --model)
            OLLAMA_MODEL="$2"
            shift 2
            ;;
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "tldr-swinton installer"
            echo ""
            echo "Usage: install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --yes, -y       Skip confirmation prompts"
            echo "  --no-ollama     Skip Ollama model setup"
            echo "  --model NAME    Ollama embedding model (default: nomic-embed-text)"
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
echo -e "${BLUE}║           tldr-swinton Installer                               ║${NC}"
echo -e "${BLUE}║   Token-efficient code analysis for LLMs                       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Confirmation
if [ "$SKIP_CONFIRM" = false ]; then
    echo -e "This will install tldr-swinton to: ${GREEN}${INSTALL_DIR}${NC}"
    echo ""
    read -p "Continue? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Step 1: Install uv if not present
echo ""
echo -e "${BLUE}[1/5]${NC} Checking for uv package manager..."

if command -v uv &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} uv is already installed: $(uv --version)"
else
    echo -e "  ${YELLOW}→${NC} Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uv &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} uv installed successfully"
    else
        echo -e "  ${RED}✗${NC} Failed to install uv"
        exit 1
    fi
fi

# Step 2: Clone or update repository
echo ""
echo -e "${BLUE}[2/5]${NC} Setting up repository..."

if [ -d "$INSTALL_DIR" ]; then
    echo -e "  ${YELLOW}→${NC} Directory exists, updating..."
    cd "$INSTALL_DIR"
    git pull --ff-only 2>/dev/null || echo -e "  ${YELLOW}!${NC} Could not update (local changes?)"
else
    echo -e "  ${YELLOW}→${NC} Cloning repository..."
    git clone https://github.com/mistakeknot/tldr-swinton "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
echo -e "  ${GREEN}✓${NC} Repository ready at ${INSTALL_DIR}"

# Step 3: Set up Python environment with uv
echo ""
echo -e "${BLUE}[3/5]${NC} Setting up Python environment..."

# Check if Python 3.11+ is available, install if not
PYTHON_VERSION=$(uv python find 2>/dev/null | head -1 || echo "")
if [ -z "$PYTHON_VERSION" ]; then
    echo -e "  ${YELLOW}→${NC} Installing Python 3.11..."
    uv python install 3.11
fi

# Create/update virtual environment and install dependencies
echo -e "  ${YELLOW}→${NC} Installing dependencies (this may take a minute)..."
if [ -f "uv.lock" ]; then
    uv sync --extra semantic 2>&1 | grep -v "^  " || true
else
    # Fallback if no lockfile
    uv venv -p 3.11 2>/dev/null || true
    uv pip install -e ".[semantic]" 2>&1 | tail -5
fi
echo -e "  ${GREEN}✓${NC} Python environment ready"

# Step 4: Set up Ollama (optional)
echo ""
echo -e "${BLUE}[4/5]${NC} Setting up Ollama embeddings..."

if [ "$SKIP_OLLAMA" = true ]; then
    echo -e "  ${YELLOW}→${NC} Skipping Ollama setup (--no-ollama)"
else
    if command -v ollama &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Ollama is installed"

        # Check if model is already pulled
        if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
            echo -e "  ${GREEN}✓${NC} Model ${OLLAMA_MODEL} is ready"
        else
            echo -e "  ${YELLOW}→${NC} Pulling ${OLLAMA_MODEL} model..."
            # Start Ollama if not running
            pgrep -x ollama > /dev/null || { ollama serve &>/dev/null & sleep 2; }
            ollama pull "$OLLAMA_MODEL"
            echo -e "  ${GREEN}✓${NC} Model ${OLLAMA_MODEL} is ready"
        fi
    else
        echo -e "  ${YELLOW}!${NC} Ollama not installed"
        echo -e "      Install from: ${BLUE}https://ollama.ai${NC}"
        echo -e "      Then run: ollama pull ${OLLAMA_MODEL}"
        echo -e "      (Semantic search will use sentence-transformers fallback)"
    fi
fi

# Step 5: Verify installation
echo ""
echo -e "${BLUE}[5/5]${NC} Verifying installation..."

# Test the CLI
if uv run tldrs --help > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} CLI is working"
else
    # Try with activated venv
    source .venv/bin/activate 2>/dev/null || true
    if tldrs --help > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} CLI is working"
    else
        echo -e "  ${RED}✗${NC} CLI verification failed"
        exit 1
    fi
fi

# Add shell alias
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

if [ -n "$SHELL_RC" ]; then
    # Add alias if not already present
    if ! grep -q "alias tldrs=" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# tldr-swinton" >> "$SHELL_RC"
        echo "alias tldrs='cd ${INSTALL_DIR} && uv run tldrs'" >> "$SHELL_RC"
        echo -e "  ${GREEN}✓${NC} Added 'tldrs' alias to ${SHELL_RC}"
    fi
fi

# Success message
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Installation Complete!                       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Usage:"
echo -e "  ${BLUE}cd ${INSTALL_DIR}${NC}"
echo -e "  ${BLUE}uv run tldrs index /path/to/project${NC}    # Build semantic index"
echo -e "  ${BLUE}uv run tldrs find \"search query\"${NC}       # Search code semantically"
echo ""
echo -e "Or after restarting your shell:"
echo -e "  ${BLUE}tldrs index /path/to/project${NC}"
echo ""
echo -e "Documentation: ${BLUE}https://github.com/mistakeknot/tldr-swinton${NC}"
