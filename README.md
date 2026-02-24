# tldrs

Token-efficient code analysis platform for LLMs and AI agents.

33 commands. 5 analysis layers. 13+ languages. 48–93% token savings.

## Why tldrs?

| For Humans | For AI Agents | For Both |
|------------|---------------|----------|
| Explore unfamiliar codebases fast | Structured context that fits in a prompt | Semantic search by meaning, not text |
| Understand call chains and data flow | Token budgets to control cost | Diff-focused context for recent changes |
| Find dead code and architectural layers | Session tracking for multi-turn work | 5-layer analysis: AST → Call Graph → CFG → DFG → PDG |

tldrs isn't just extraction: it's full static analysis (control flow, data flow, program slicing), semantic search (embeddings + BM25 hybrid), and session-aware artifact storage, all designed to produce the smallest context an LLM needs to do its job.

## Quick start

### Install

```bash
# One-liner (recommended)
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/install.sh | bash

# Or via uv
uv pip install tldr-swinton

# Or manual
git clone https://github.com/mistakeknot/tldr-swinton
cd tldr-swinton && uv sync --extra semantic-ollama
```

### Try it

```bash
tldrs structure src/              # Code structure (functions, classes, imports)
tldrs diff-context --project .    # Context pack for your recent changes
tldrs index . && tldrs find "authentication logic"   # Semantic search
tldrs context main --project .    # Call-graph context around a symbol
```

### Verify

```bash
tldrs --version   # 0.7.0
tldrs doctor      # Check optional tools (type checkers, linters)
```

## Commands

All 33 top-level commands grouped by use case. Each command supports `--help` for full options.

### Reconnaissance

Get oriented in a codebase or understand recent changes.

| Command | Description |
|---------|-------------|
| `diff-context` | Diff-focused context pack (merge-base → HEAD) |
| `context` | Call-graph context around a symbol (`--depth`, `--budget`, `--format`) |
| `find` | Semantic code search (requires `tldrs index` first) |
| `structural` | Structural search using ast-grep patterns |
| `search` | Regex pattern search across files |
| `quickstart` | Quick reference guide for AI agents |

### Structure & extraction

Understand file and project organization.

| Command | Description |
|---------|-------------|
| `structure` | Code structure: functions, classes, imports (codemaps) |
| `extract` | Full file analysis as JSON |
| `tree` | File tree |
| `imports` | Parse imports from a source file |
| `importers` | Reverse import lookup: find all files importing a module |

### Deep analysis

Static analysis beyond surface-level extraction.

| Command | Description |
|---------|-------------|
| `cfg` | Control flow graph for a function |
| `dfg` | Data flow graph for a function |
| `slice` | Program slice: what affects a specific line |
| `calls` | Cross-file call graph |
| `impact` | Reverse call graph: find all callers of a function |
| `dead` | Find unreachable (dead) code |
| `arch` | Detect architectural layers from call patterns |
| `change-impact` | Find tests affected by changed files |
| `diagnostics` | Type checker and linter diagnostics |
| `distill` | Compress context for sub-agent consumption |
| `hotspots` | Most frequently used symbols across sessions |

### Semantic search

Embedding-based search: find code by meaning, not keywords.

| Command | Description |
|---------|-------------|
| `index` | Build or update the semantic index (`--backend ollama\|sentence-transformers\|auto`) |
| `find` | Query the index (e.g., `tldrs find "error handling patterns"`) |
| `semantic` | Low-level semantic search subcommands |

### Infrastructure

Daemon, caching, and health checks.

| Command | Description |
|---------|-------------|
| `daemon` | Daemon management (start, stop, status) |
| `warm` | Pre-build call graph cache for faster queries |
| `prebuild` | Precompute context bundle for current HEAD |
| `doctor` | Check and install diagnostic tools |
| `presets` | List flag presets and their expansions |
| `manifest` | Machine-readable JSON of all tldrs capabilities |

### Artifact storage

Persistent storage for agent workflows.

| Command | Description | Subcommands |
|---------|-------------|-------------|
| `vhs` | Content-addressed store for tool outputs | 9 (`put`, `get`, `cat`, `has`, `info`, `rm`, `ls`, `stats`, `gc`) |
| `wb` | Agent workbench: capsules, decisions, hypotheses | 18 (`capture`, `show`, `decide`, `hypothesis`, `link`, ...) |
| `bench` | Benchmarking harness for agent improvements | 4 (`run`, `list`, `report`, `compare`) |

## Agent integration

### Claude code plugin

```bash
/plugin marketplace add mistakeknot/interagency-marketplace
/plugin install tldr-swinton
```

Adds 6 slash commands (`/tldrs-find`, `/tldrs-diff`, `/tldrs-context`, `/tldrs-structural`, `/tldrs-quickstart`, `/tldrs-extract`) and 6 autonomous skills that fire before Read/Grep to suggest better reconnaissance.

### MCP server

```bash
uv pip install mcp
tldr-mcp --project /path/to/project
```

Exposes tldrs commands as MCP tools: 1:1 mapping with the CLI. Add to your MCP config:

```json
{
  "mcpServers": {
    "tldrs": {
      "command": "tldr-mcp",
      "args": ["--project", "/path/to/project"]
    }
  }
}
```

### Generic CLI (Any agent)

Any agent with shell access can call `tldrs` directly:

```bash
# Decision tree: which command?
# Working on recent changes?     → tldrs diff-context --project .
# Need context around a symbol?  → tldrs context <name> --project . --budget 2000
# Searching for code by meaning? → tldrs find "query"
# Need file/project structure?   → tldrs structure src/ --lang python
# Tracing data or control flow?  → tldrs cfg/dfg/slice <file> <func>
```

## Benchmarks

| Eval | What It Measures | Result |
|------|-----------------|--------|
| DiffLens | Diff-focused context vs diff+deps baseline | **48% token savings**, ~0.77s latency |
| Token efficiency | Compact signatures vs full files | **93% savings** (compact), **66%** (structure JSON) |
| Semantic search | Search results vs entire repo | **85% token savings**, top-1 accuracy on auth/db |
| Agent workflow | Realistic editing tasks with full context | **50–85% savings** (varies by compression) |

Agent workflow detail: 53% (none) → 78% (two-stage) → 84% (chunk-summary) at budget=2000.

**Reproduce:**
```bash
uv run python evals/difflens_eval.py
uv run python evals/token_efficiency_eval.py
uv run python evals/semantic_search_eval.py
uv run python evals/agent_workflow_eval.py --compress chunk-summary
```

See [docs/token-savings-summary.md](docs/token-savings-summary.md) for full methodology and per-task breakdown.

## Language support

| Tier | Languages | Install |
|------|-----------|---------|
| **Full** (always available) | Python, TypeScript, JavaScript, Rust, Go, Java, C, C++, Ruby | Included |
| **Optional** (extra grammars) | Kotlin, Swift, C#, Scala, Lua, Elixir | `uv pip install tldr-swinton[all]` |

All languages use tree-sitter for parsing (Python also supports native AST). Language is auto-detected from file extensions.

## Architecture

```
                         ┌─────────────────────────────────────┐
                         │             tldrs CLI               │
                         └──────────────┬──────────────────────┘
                                        │
           ┌────────────┬───────────────┼───────────────┬──────────────┐
           │            │               │               │              │
     ┌─────▼─────┐ ┌───▼────┐ ┌───────▼────────┐ ┌───▼────┐ ┌──────▼──────┐
     │ Extraction │ │ Search │ │ Static Analysis│ │ Engines│ │  Artifacts  │
     │            │ │        │ │                │ │        │ │             │
     │ structure  │ │ index  │ │ cfg  dfg  pdg  │ │symbol- │ │ vhs  wb     │
     │ extract    │ │ find   │ │ slice  calls   │ │ kite   │ │ bench       │
     │ tree       │ │ search │ │ dead  impact   │ │diff-   │ │ daemon      │
     │ imports    │ │ struct-│ │ arch  change-  │ │ lens   │ │             │
     │            │ │  ural  │ │       impact   │ │        │ │             │
     └────────────┘ └────────┘ └────────────────┘ └────────┘ └─────────────┘

  5-Layer Analysis Pipeline:
  AST → Call Graph → CFG → DFG → PDG
```

- **Extraction**: Tree-sitter + Python AST parsing → signatures, types, classes, imports
- **Search**: Semantic embeddings (Ollama/sentence-transformers) + BM25 hybrid with RRF fusion
- **Static Analysis**: Control flow, data flow, program slicing, call graphs, dead code detection
- **Engines**: SymbolKite (call-graph context) and DiffLens (diff-focused context) produce `ContextPack` objects
- **Artifacts**: VHS (content-addressed output store), Workbench (agent reasoning), Bench (evals)

## Installation details

### Optional dependencies

| Group | What It Adds | Install |
|-------|-------------|---------|
| `semantic-ollama` | FAISS, NumPy, BM25 (for Ollama embeddings) | `uv pip install tldr-swinton[semantic-ollama]` |
| `semantic` | Above + sentence-transformers + torch (1.3GB) | `uv pip install tldr-swinton[semantic]` |
| `full` | Above + Ollama client + tiktoken | `uv pip install tldr-swinton[full]` |
| `all` | Additional tree-sitter grammars (6 languages) | `uv pip install tldr-swinton[all]` |
| `test` | pytest | `uv pip install tldr-swinton[test]` |

### Ollama setup (Recommended for semantic search)

```bash
# Install Ollama: https://ollama.ai
ollama pull nomic-embed-text-v2-moe   # 274MB, 768d embeddings
tldrs index .                          # Build the index
```

### Development

```bash
git clone https://github.com/mistakeknot/tldr-swinton
cd tldr-swinton
uv sync --extra full
```

### Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/uninstall.sh | bash
```

Removes installation directory, shell alias, and pip packages. Project indexes (`.tldrs/` directories) are preserved.

## Output formats & presets

**Presets** expand to multiple flags for common workflows:

| Preset | Expands To |
|--------|-----------|
| `compact` | `--format ultracompact --budget 2000 --compress-imports --strip-comments` |
| `minimal` | `--format ultracompact --budget 1500 --compress two-stage --compress-imports --strip-comments --type-prune` |
| `multi-turn` | `--format cache-friendly --budget 2000 --session-id auto --delta` |

Usage: `tldrs context main --project . --preset compact`

**Available formats:** `json`, `json-pretty`, `ultracompact`, `cache-friendly`, `packed-json`, `columnar-json`

## Links

- [Quick Reference](docs/QUICKSTART.md): One-page agent guide
- [Agent Workflow](docs/agent-workflow.md): Full integration guide
- [Token Savings](docs/token-savings-summary.md): Detailed benchmark methodology
- [AGENTS.md](AGENTS.md): Architecture, commands, and development guide

## Credits

Fork of [llm-tldr](https://github.com/parcadei/llm-tldr) by [parcadei](https://github.com/parcadei).

## License

MIT
