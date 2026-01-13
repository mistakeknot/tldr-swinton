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

## Installation

```bash
pip install tldr-swinton
```

### For AI Coding Agents

If you're an AI agent setting up this project for a user, follow these steps:

```bash
# 1. Clone the repository
git clone https://github.com/mistakeknot/tldr-swinton
cd tldr-swinton

# 2. Install in development mode with semantic search support
pip install -e ".[semantic]"

# 3. (Recommended) Set up Ollama for fast local embeddings
#    Check if Ollama is installed:
which ollama || echo "Ollama not installed - see https://ollama.ai for installation"
#    If installed, ensure it's running and pull the embedding model:
pgrep -x ollama || ollama serve &
ollama pull nomic-embed-text

# 4. Verify installation
tldrs --help

# 5. (Optional) Create .tldrignore to exclude files (uses .gitignore syntax)
echo -e "node_modules/\ndist/\n*.min.js" > /path/to/project/.tldrignore

# 6. Build semantic index for a project (~1-3 min for large projects)
tldrs index /path/to/project

# 7. Verify semantic search works
tldrs index --info              # Check index stats
tldrs find "authentication"     # Test a search query
```

**Requirements:**
- Python 3.10+
- For semantic search embeddings, one of:
  - **Ollama** (recommended): Install from https://ollama.ai, then `ollama pull nomic-embed-text` (274MB)
  - **sentence-transformers** (fallback): Automatically downloads BGE model on first use (1.3GB)

### For Development

```bash
git clone https://github.com/mistakeknot/tldr-swinton
cd tldr-swinton
pip install -e ".[full]"  # Includes Ollama client + tiktoken
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
pip install tldr-swinton[semantic]  # Adds FAISS + sentence-transformers

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
