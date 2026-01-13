# AGENTS.md - AI Agent Instructions for tldr-swinton

This document provides instructions for all AI coding assistants (Claude, Codex, etc.) working with the tldr-swinton codebase.

## Project Overview

tldr-swinton is a token-efficient code analysis tool for LLMs. It's a fork of llm-tldr with fixes for TypeScript and Rust support.

**Key directories:**
- `src/tldr_swinton/` - Main Python package
- `evals/` - Evaluation scripts for token efficiency

## Quick Reference

```bash
# Install (development)
pip install -e .
pip install -e ".[semantic]"  # With semantic search (FAISS + sentence-transformers)
pip install -e ".[full]"      # Full stack (includes Ollama + tiktoken)

# Test commands
tldrs extract src/tldr_swinton/embeddings.py    # Extract file info
tldrs structure src/                             # Show code structure
tldrs find "authentication logic"                # Semantic search (requires index)
tldrs index .                                    # Build semantic index

# After code changes
find . -name "*.pyc" -delete && find . -name "__pycache__" -type d -exec rm -rf {} +
pip install -e .
```

## Architecture

### Core Extraction Pipeline

```
CLI (cli.py)
    ↓
API layer (api.py)
    ↓
extract_file() → HybridExtractor.extract()
    ↓
Language-specific extraction:
  - Python: Native AST (ast_extractor.py)
  - TypeScript/Rust/Go/etc: tree-sitter (hybrid_extractor.py)
  - Fallback: Pygments signatures
    ↓
ModuleInfo with FunctionInfo objects
    ↓
.to_dict() for JSON serialization
```

### Semantic Search Pipeline (v0.2.0)

```
tldrs index .  → embeddings.py (Ollama/sentence-transformers)
                      ↓
               vector_store.py (FAISS IndexFlatIP)
                      ↓
               .tldr/index/{vectors.faiss, units.json, meta.json}

tldrs find "query" → index.py:search_index() → VectorStore.search()
                          ↓
                    Lexical fast-path for identifiers (exact match)
                          ↓
                    Semantic search for natural language queries
```

### Key Data Structures

**FunctionInfo** (`ast_extractor.py:27`):
```python
@dataclass
class FunctionInfo:
    name: str
    params: list[str]
    return_type: str | None
    docstring: str | None
    is_method: bool = False
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    line_number: int = 0
    language: str = "python"  # Controls signature() output format
```

The `language` field is critical - it determines the output format of `signature()`:
- `"typescript"` → `async function name(params): Type`
- `"rust"` → `fn name(params) -> Type`
- `"python"` (default) → `def name(params) -> Type`

**ModuleInfo** (`ast_extractor.py:131`): Container for file analysis results.

**CodeUnit** (`vector_store.py`): Minimal metadata for semantic search results.

### Language Support

Language detection happens in multiple places:
1. `cli.py:EXTENSION_TO_LANGUAGE` - Maps file extensions to language names
2. `hybrid_extractor.py:_detect_language()` - Runtime detection from extension
3. `api.py:get_code_structure()` - Auto-detection for single files

## Critical Rules

### Import Convention

All internal imports MUST use relative imports:
```python
# CORRECT
from .hybrid_extractor import HybridExtractor
from .ast_extractor import FunctionInfo

# WRONG - imports from old llm-tldr package!
from tldr.hybrid_extractor import HybridExtractor
```

### Language Field Required

When creating `FunctionInfo` objects for non-Python languages, ALWAYS set the `language` field:
```python
FunctionInfo(
    name=func_name,
    params=params,
    return_type=return_type,
    docstring=None,
    language="typescript",  # REQUIRED for correct signature format
)
```

### Function Name Cleaning

TypeScript/JavaScript function names must be cleaned of modifiers:
```python
for prefix in ("export ", "async ", "default "):
    if name.startswith(prefix):
        name = name[len(prefix):]
```

### Embeddings Must Be L2-Normalized

FAISS IndexFlatIP expects normalized vectors for cosine similarity:
```python
embedding = embedding / np.linalg.norm(embedding)  # Required!
```

### Incremental Index Updates

`build_index()` reconstructs vectors for unchanged files (via `store.reconstruct_all_vectors()`). Only new/changed files get re-embedded.

## Common Tasks

### Adding a New Language

1. Add tree-sitter grammar to `pyproject.toml` dependencies
2. Add extension mapping in `cli.py:EXTENSION_TO_LANGUAGE`
3. Add signature format in `FunctionInfo.signature()` (`ast_extractor.py`)
4. Add extraction method in `HybridExtractor` (`hybrid_extractor.py`)
5. Add to language maps in `api.py:get_code_structure()`

### Fixing Signature Formatting

The `FunctionInfo.signature()` method (`ast_extractor.py:39-84`) handles all signature formatting. Each language has a branch:

```python
if self.language in ("typescript", "tsx", "javascript"):
    return f"{async_prefix}function {self.name}({params_str}){ret}"
elif self.language == "rust":
    return f"{async_prefix}fn {self.name}({params_str}){ret_rust}"
# ... etc
```

### Semantic Search Backends

```bash
# Check available backends
python -c "from tldr_swinton.embeddings import check_backends; print(check_backends())"

# Ollama (preferred - fast, local)
ollama pull nomic-embed-text
tldrs index . --backend ollama

# sentence-transformers (fallback - 1.3GB download)
tldrs index . --backend sentence-transformers

# Auto (tries Ollama first, falls back)
tldrs index . --backend auto
```

## Debugging

### Verify Correct Module Loaded

```bash
python -c "import tldr_swinton; print(tldr_swinton.__file__)"
python -c "from tldr_swinton.hybrid_extractor import HybridExtractor; import inspect; print(inspect.getfile(HybridExtractor))"
```

### Test Extraction Directly

```bash
python -c "
from tldr_swinton.hybrid_extractor import HybridExtractor
e = HybridExtractor()
r = e.extract('path/to/file.ts')
for f in r.functions[:3]:
    print(f'{f.name}: {f.language} -> {f.signature()}')
"
```

### Check for Import Issues

```bash
grep -r "from tldr\." src/tldr_swinton/ --include="*.py"
```
Should return empty - all imports should be relative (`.`).

### Check Index Health

```bash
tldrs index --info                    # Show index stats
ls -la .tldr/index/                   # Check index files exist
```

## Testing

### Manual Testing

```bash
# TypeScript - should show "function" not "def"
tldrs extract path/to/file.ts | grep signature

# Rust - should show "fn" not "def"
tldrs extract path/to/file.rs | grep signature

# Single file structure - should work and detect language
tldrs structure path/to/file.ts | grep language
```

### After Making Changes

1. Clear Python cache:
   ```bash
   find . -name "*.pyc" -delete
   find . -name "__pycache__" -type d -exec rm -rf {} +
   ```

2. Reinstall in development mode:
   ```bash
   pip install -e .
   ```

3. Verify the correct module is loaded:
   ```bash
   python -c "import tldr_swinton; print(tldr_swinton.__file__)"
   ```

### Evals

```bash
# Token efficiency eval (basic)
python evals/token_efficiency_eval.py

# Semantic search eval
python evals/semantic_search_eval.py

# Agent workflow eval (realistic Claude Code scenarios)
python evals/agent_workflow_eval.py
```

The agent workflow eval tests real token savings for code modification tasks (not just search output vs raw code).

## File Reference

| File | Purpose |
|------|---------|
| `cli.py` | CLI entry point, argument parsing |
| `api.py` | High-level API functions |
| `ast_extractor.py` | Data structures, Python extraction |
| `hybrid_extractor.py` | Multi-language extraction via tree-sitter |
| `cfg_extractor.py` | Control flow graph extraction |
| `dfg_extractor.py` | Data flow graph extraction |
| `pdg_extractor.py` | Program dependency graph |
| `signature_extractor_pygments.py` | Fallback signature extraction |
| `embeddings.py` | Ollama/sentence-transformers embedding backend |
| `vector_store.py` | FAISS vector storage wrapper |
| `index.py` | Semantic index management |
| `semantic.py` | Original semantic search (5-layer embeddings) |

## Version History

- **0.2.0** - Semantic search with Ollama support
  - Added `tldrs index` - Build semantic index with Ollama or sentence-transformers
  - Added `tldrs find` - Natural language code search
  - Added `embeddings.py` - Multi-backend embedding support (Ollama/HuggingFace)
  - Added `vector_store.py` - FAISS wrapper with persistent storage
  - Added `index.py` - Index management with incremental updates
  - Index stored in `.tldr/index/` (vectors.faiss, units.json, meta.json)

- **0.1.0** - Initial fork with TypeScript/Rust signature fixes
  - Fixed `FunctionInfo.signature()` to be language-aware
  - Fixed function name cleaning for TypeScript
  - Fixed single file support in `structure` command
  - Fixed internal imports (tldr → tldr_swinton)
