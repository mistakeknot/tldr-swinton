# tldr-swinton

Token-efficient code analysis for LLMs - a fork of [llm-tldr](https://github.com/parcadei/llm-tldr) with improved TypeScript and Rust support.

## Why This Fork?

The original llm-tldr had several issues with non-Python languages:
- All function signatures showed Python's `def` keyword regardless of language
- TypeScript function names included `export async` prefixes
- The `structure` command only worked on directories, not single files

This fork fixes those issues while maintaining full compatibility with the original API.

## Key Improvements

| Issue | Before | After |
|-------|--------|-------|
| TypeScript signatures | `async def initCache() -> Promise<void>` | `async function initCache(): Promise<void>` |
| Rust signatures | `def process(x: &str) -> Result<()>` | `fn process(x: &str) -> Result<()>` |
| Function names | `export async initCache` | `initCache` |
| Single file analysis | Not supported | Fully supported |

## Benchmarks (2026-01-15)

| Eval | Measures | Headline |
|------|----------|----------|
| DiffLens (avg across Python/TS/Rust) | Diff-focused context vs diff+deps baseline | **48.0% token savings** at **~0.77s** avg latency |
| Token efficiency eval | Compact + structure savings vs raw | **93.1%** compact savings, **62.4%** structure JSON savings |
| Semantic search eval | Retrieval + token footprint | **84.8%** token savings; top-1 auth/db, cache in top-3 |
| Agent workflow eval | Realistic agent scenarios | **83.6%** aggregate savings (chunk-summary, budget=2000) |

**Methodology highlights:**
- DiffLens baseline uses **diff+deps** (changed files + direct local imports). Diff-only may be negative and is reported in the eval output.
- Metrics come from the built-in eval scripts in `evals/` and are reproducible locally.
- Agent workflow eval uses diff-context for the "context pack" step: **61.2%** (none), **77.6%** (two-stage), **83.6%** (chunk-summary) at budget=2000.

**Reproduce:**
```bash
.venv/bin/python evals/difflens_eval.py
.venv/bin/python evals/token_efficiency_eval.py
.venv/bin/python evals/semantic_search_eval.py
.venv/bin/python evals/agent_workflow_eval.py
.venv/bin/python evals/agent_workflow_eval.py --compress two-stage
.venv/bin/python evals/agent_workflow_eval.py --compress chunk-summary
```

## Installation

### One-Liner (Recommended for AI Agents)

```bash
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/install.sh | bash
```

This installs everything automatically:
- Installs [uv](https://github.com/astral-sh/uv) package manager if needed
- Clones the repository to `~/tldr-swinton`
- Creates a Python virtual environment
- Installs all dependencies
- Sets up Ollama embedding model (if Ollama is installed)
- Adds a `tldrs` shell alias

Quick verify after install:
```bash
tldrs --help
tldrs context main --project . --depth 1 --budget 200 --format ultracompact
```

Options:
```bash
# Skip prompts (for automation)
curl -fsSL ... | bash -s -- --yes

# Skip Ollama setup
curl -fsSL ... | bash -s -- --no-ollama

# Custom install directory
curl -fsSL ... | bash -s -- --dir /path/to/install
```

### Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/uninstall.sh | bash
```

This removes the installation directory, shell alias, and pip packages. Project indexes (`.tldrs/` directories) are preserved by default.

### Quick Install (pip)

```bash
pip install tldr-swinton
```

### Optional: MCP Server

The MCP server is optional. If you want MCP tools, install the MCP dependency:
```bash
pip install mcp
```

Then run:
```bash
tldr-mcp --project .
```

### Optional: Codex/Claude Skills

- **Codex**: repo-scoped skill lives at `.codex/skills/tldrs-agent-workflow/` (uses the CLI workflow).
- **Claude**: create a custom skill with the same steps from `docs/agent-workflow.md`.

### Manual Setup (Step-by-Step)

If you prefer manual control or the one-liner doesn't work:

```bash
# 1. Clone the repository
git clone https://github.com/mistakeknot/tldr-swinton
cd tldr-swinton

# 2. Install with uv (recommended) or pip
# Ollama-only (no torch):
uv sync --extra semantic-ollama    # Fast, light-weight
# OR
pip install -e ".[semantic-ollama]"
#
# If you need sentence-transformers fallback (no Ollama):
uv sync --extra semantic
# OR
pip install -e ".[semantic]"

# Note: `tldrs index`/`tldrs find` require one of the semantic extras above.

# 3. (Recommended) Set up Ollama for fast local embeddings
#    Install from https://ollama.ai, then:
ollama pull nomic-embed-text

# 4. Verify installation
tldrs --help

# 5. Build semantic index for a project
tldrs index /path/to/project

# 6. Search!
tldrs find "authentication logic"
```

### Optional: Store Outputs in tldrs-vhs

If you have the separate `tldrs-vhs` CLI installed, you can store large
context outputs as `vhs://` references instead of printing inline:

```bash
# Install tldrs-vhs (separate repo)
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldrs-vhs/main/scripts/install.sh | bash

# Non-interactive shells/CI may not load aliases:
export TLDRS_VHS_CMD="$HOME/tldrs-vhs/.venv/bin/tldrs-vhs"

# Store context output in vhs store
tldrs context main --project . --output vhs

# Output includes the ref on the first line plus a short summary + preview
# (max 30 lines / 2 KB, full lines only)

# Append a stored ref into output
tldrs context main --project . --include vhs://<hash>
```

### Agent Snippets (AGENTS.md / CLAUDE.md)

Copy/paste this into a project’s `AGENTS.md` or `CLAUDE.md` to enable
DiffLens and VHS usage for coding agents:

Full workflow guide: see `docs/agent-workflow.md`.

```md
## DiffLens + VHS (Agent Context)

# Install tldrs-vhs (https://github.com/mistakeknot/tldrs-vhs)
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldrs-vhs/main/scripts/install.sh | bash

# Decision guide (which tool to use when):
# 1) Working on recent changes? -> DiffLens first:
#    tldrs diff-context --project . --budget 2000
# 2) Need call-graph context around a symbol? -> SymbolKite:
#    tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact
# 3) Need structure of a folder/file? -> Structure/Extract:
#    tldrs structure src/ --lang typescript
#    tldrs extract path/to/file.ts
# 4) Need semantic search? -> Index + Find:
#    tldrs index .
#    tldrs find "authentication logic"

# Diff-first context for current changes
tldrs diff-context --project . --budget 2000

# Store large context outputs as refs
tldrs context main --project . --output vhs

# Expand a stored ref inline when needed
tldrs context main --project . --include vhs://<hash>

# Notes:
# - diff-context defaults to merge-base(main/master) → HEAD
# - vhs output prints ref + summary/preview (30 lines / 2 KB)
# - ultracompact format saves tokens (`--format ultracompact`)
# - `context --format json` returns ContextPack JSON for tooling
# - ambiguous entries return candidate lists (re-run with file-qualified entry)
# - suppress ambiguous entry warnings with TLDRS_NO_WARNINGS=1
# - Optional overrides:
#   - TLDRS_VHS_CMD="python -m tldrs_vhs.cli"
#   - TLDRS_VHS_PYTHONPATH=/path/to/tldrs-vhs/src
```

### DiffLens (Diff-First Context for Agents)

Use DiffLens to generate a compact, diff-focused context pack for the current
working tree (or a specific commit range). This is ideal for coding agents
because it prioritizes changed symbols and their immediate dependencies.

```bash
# Default: merge-base with main/master → HEAD (ultracompact output)
tldrs diff-context --project .

# Explicit range
tldrs diff-context --project . --base HEAD~1 --head HEAD

# JSON output for tooling
tldrs diff-context --project . --format json

# Budgeted output (approx tokens)
tldrs diff-context --project . --budget 2000

# Experimental compression (prototypes)
tldrs diff-context --project . --compress two-stage
tldrs diff-context --project . --compress chunk-summary
```

**DiffLens JSON schema notes (2026-01-14):**
- `--format json` is compact (no indentation); use `--format json-pretty` for debugging.
- `signatures_only` was removed; infer signature-only slices from `code == null`.
- `diff_lines` is range-encoded (e.g., `[[1,3],[5,6]]`).
- `code` is windowed around diffs with `...` separators.
- Experimental compression adds `block_count` and `dropped_blocks` per slice.
- Chunk-summary compression adds `summary` per slice and omits `code`.

**Requirements:**
- Python 3.10+
- For semantic search embeddings, one of:
  - **Ollama** (recommended): Install from https://ollama.ai, then `ollama pull nomic-embed-text` (274MB)
  - **sentence-transformers** (fallback): Automatically downloads BGE model on first use (1.3GB)

### For Development

```bash
git clone https://github.com/mistakeknot/tldr-swinton
cd tldr-swinton
uv sync --extra full    # Includes Ollama client + tiktoken
# OR
pip install -e ".[full]"
```

## Quick Start

```bash
# Extract full info from a file (JSON output)
tldrs extract src/app.ts

# Show code structure for a directory
tldrs structure src/ --lang typescript

# Show code structure for a single file (auto-detects language)
tldrs structure src/app.ts

# Get LLM-ready context for a function
tldrs context myFunction --project src/

# Search for patterns
tldrs search "async.*fetch" src/
```

## Commands

### Basic Analysis

| Command | Description |
|---------|-------------|
| `tldrs tree [path]` | Show file tree |
| `tldrs structure [path]` | Show code structure (functions, classes, imports) |
| `tldrs extract <file>` | Extract full file info as JSON |
| `tldrs search <pattern> [path]` | Search files for regex pattern |

### Advanced Analysis

| Command | Description |
|---------|-------------|
| `tldrs context <entry> [--project]` | Get LLM-ready context for a function/class |
| `tldrs cfg <file> <function>` | Control flow graph |
| `tldrs dfg <file> <function>` | Data flow graph |
| `tldrs slice <file> <func> <line>` | Program slice (what affects a line) |
| `tldrs calls [path]` | Build project call graph |
| `tldrs impact <function> [path]` | Find all callers of a function |

### Semantic Search (NEW)

Semantic code search using embeddings - find code by meaning, not just text patterns.

| Command | Description |
|---------|-------------|
| `tldrs index [path]` | Build semantic index (first time or after changes) |
| `tldrs find <query>` | Search code semantically (e.g., "authentication logic") |
| `tldrs index --info` | Show index statistics |

```bash
# First, build the index (takes ~30s for medium projects)
tldrs index .

# Then search by meaning
tldrs find "error handling patterns"
tldrs find "database connection setup"
tldrs find "user authentication flow"
```

**Backend Options:**
- `--backend ollama` - Use Ollama (fast, local, requires [Ollama](https://ollama.ai) + `ollama pull nomic-embed-text`)
- `--backend sentence-transformers` - Use HuggingFace BGE model (1.3GB download on first use)
- `--backend auto` (default) - Try Ollama first, fall back to sentence-transformers

**Installation for semantic search:**
```bash
pip install tldr-swinton[semantic-ollama]  # FAISS + NumPy only (for Ollama)
# OR, if you need sentence-transformers fallback:
pip install tldr-swinton[semantic]  # Adds FAISS + sentence-transformers (+ torch)

# (Recommended) Also install Ollama for faster embeddings:
# See https://ollama.ai for installation, then:
ollama pull nomic-embed-text
```

### Output Formats

Most commands output JSON by default. Use `--format compact` for token-efficient output suitable for LLM context windows.

## Supported Languages

| Language | Signature Format | Tree-sitter Support |
|----------|------------------|---------------------|
| TypeScript/JavaScript | `function name(params): Type` | Full |
| Rust | `fn name(params) -> Type` | Full |
| Python | `def name(params) -> Type` | Full (native AST) |
| Go | `func name(params) Type` | Full |
| Java | `Type name(params)` | Full |
| C/C++ | `Type name(params)` | Full |
| Ruby | `def name(params)` | Full |
| Kotlin | `fun name(params): Type` | Optional |
| Swift | `func name(params) -> Type` | Optional |
| C# | `Type name(params)` | Optional |
| Scala | `def name(params): Type` | Optional |
| Lua | `function name(params)` | Optional |
| Elixir | `def name(params)` | Optional |

Languages marked "Optional" require installing additional tree-sitter grammars:

```bash
pip install tldr-swinton[all]
```

## Architecture

tldr-swinton provides 5 layers of code analysis:

1. **Layer 1: AST** - Signatures, types, classes, imports
2. **Layer 2: Call Graph** - Who calls what, entry points
3. **Layer 3: CFG** - Control flow, branches, loops, complexity
4. **Layer 4: DFG** - Data flow, def-use chains
5. **Layer 5: PDG** - Program dependencies, slicing

Each layer can be accessed separately (ARISTODE pattern) or combined.

## Engines

Discrete context strategies now live under `tldr_swinton.engines.*` as stable
entry points (SymbolKite, DiffLens, CFG, DFG, PDG, Slice). The `api.py` wrappers
remain for backward compatibility.

## Example Output

```bash
$ tldrs extract src/services/auth.ts
```

```json
{
  "file_path": "src/services/auth.ts",
  "language": "typescript",
  "functions": [
    {
      "name": "validateToken",
      "signature": "async function validateToken(token: string): Promise<boolean>",
      "params": ["token: string"],
      "return_type": "Promise<boolean>",
      "is_async": true,
      "line_number": 15
    }
  ],
  "classes": [],
  "imports": [
    {"module": "jsonwebtoken", "names": ["verify", "decode"]}
  ]
}
```

## Integration with LLMs

tldr-swinton is designed to provide token-efficient context for AI coding assistants:

```bash
# Get context for a function you're working on
tldrs context handleAuth --project src/ > context.txt

# The output includes:
# - Function signature and implementation
# - Functions it calls (with signatures)
# - Functions that call it
# - Relevant imports and types
```

## Token Efficiency (Verified)

Measured using tiktoken (cl100k_base encoding):

| Format | Avg. Token Savings |
|--------|-------------------|
| Compact (function names only) | **93%** |
| Structure JSON | **62%** |

Run the evaluation yourself:
```bash
pip install tiktoken
python evals/token_efficiency_eval.py
```

## Credits

Original project by [parcadei](https://github.com/parcadei/llm-tldr).

## License

MIT
