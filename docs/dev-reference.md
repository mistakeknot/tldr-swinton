# Dev Reference (tldr-swinton)

Detailed development procedures extracted from AGENTS.md. For the quick reference, see AGENTS.md.

## Adding a New Language

1. Add tree-sitter grammar to `pyproject.toml` dependencies
2. Add extension mapping in `cli.py:EXTENSION_TO_LANGUAGE`
3. Add signature format branch in `FunctionInfo.signature()` (`modules/core/ast_extractor.py`)
4. Add extraction method in `HybridExtractor` (`modules/core/hybrid_extractor.py`)
5. Add to language maps in `modules/core/api.py:get_code_structure()`

## Debugging

### Verify Correct Module Loaded

```bash
python -c "import tldr_swinton; print(tldr_swinton.__file__)"
python -c "from tldr_swinton.modules.core.hybrid_extractor import HybridExtractor; import inspect; print(inspect.getfile(HybridExtractor))"
```

### Test Extraction Directly

```bash
python -c "
from tldr_swinton.modules.core.hybrid_extractor import HybridExtractor
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
Should return empty -- all imports must be relative (`.`).

### Check Index Health

```bash
tldrs index --info                    # Show index stats
ls -la .tldrs/index/                   # Check index files exist
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
   find . -name "*.pyc" -delete && find . -name "__pycache__" -type d -exec rm -rf {} +
   ```

2. Reinstall in development mode:
   ```bash
   uv pip install -e .
   ```

3. Verify the correct module is loaded (see Debugging section above).

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

## ContextPack Notes

- `tldrs context --format json` returns ContextPack JSON (slices; signature-only slices have `code: null`).
- Each ContextPack slice includes `etag` (signature + code hash).
- Ambiguous entries return candidate lists; re-run with `file.py:func`.
- For API tests, use `get_symbol_context_pack(..., etag=...)` to get `"UNCHANGED"`.

## VHS Ref Storage

For large outputs, store as VHS refs:
```bash
tldrs context <entry> --project . --output vhs
tldrs context <entry> --project . --include vhs://<hash>
```

If `tldrs-vhs` isn't on PATH (non-interactive shells), set:
```bash
export TLDRS_VHS_CMD="$HOME/tldrs-vhs/.venv/bin/tldrs-vhs"
```

Repo-local VHS storage lives under `.tldrs/` by default. Override: `export TLDRS_VHS_HOME=/path/to/store`.

## Compression Promotion Gate

Experimental compression modes (`--compress two-stage|chunk-summary`) **must not be promoted to default** until they pass:
- **>=10% additional savings** vs the current diff+deps baseline on `evals/difflens_eval.py`
- **No regressions** on `evals/agent_workflow_eval.py`
- **At least one manual spot check** on a real repo (correctness/readability)

## Version History

- **0.7.5** - ColBERT late-interaction search backend (SearchBackend protocol, dual backend, PLAID centroid drift enforcement)
- **0.6.2** - interbench sync automation (`tldrs manifest`, `/tldrs-interbench-sync` skill)
- **0.6.1** - Delta engine extraction, parser caching
- **0.6.0** - Wave 2+3 features wired into pipeline
- **0.5.0** - Skill-first plugin, structural search, BM25 hybrid, compression upgrades
- **0.4.0** - Output caps, benchmark infrastructure
- **0.3.0** - Embedding and search upgrades (nomic-embed-text-v2-moe, BM25 RRF)
- **0.2.0** - Semantic search with Ollama support
- **0.1.0** - Initial fork with TypeScript/Rust signature fixes
