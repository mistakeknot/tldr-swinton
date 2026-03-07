# Critical Rules

## Import Convention

All internal imports MUST use relative imports:
```python
# CORRECT
from .hybrid_extractor import HybridExtractor
from .ast_extractor import FunctionInfo

# WRONG - imports from old llm-tldr package
from tldr.hybrid_extractor import HybridExtractor
```

## Language Field Required

When creating `FunctionInfo` for non-Python languages, ALWAYS set the `language` field:
```python
FunctionInfo(name=func_name, params=params, return_type=return_type,
             language="typescript")  # Controls signature() output format
```

The `language` field determines signature format:
- `"typescript"` -> `async function name(params): Type`
- `"rust"` -> `fn name(params) -> Type`
- `"python"` (default) -> `def name(params) -> Type`

## Function Name Cleaning

TypeScript/JavaScript function names must be cleaned of modifiers:
```python
for prefix in ("export ", "async ", "default "):
    if name.startswith(prefix):
        name = name[len(prefix):]
```

## Embeddings Must Be L2-Normalized (FAISS Backend)

FAISS `IndexFlatIP` expects normalized vectors for cosine similarity. Handled by `_l2_normalize()` in `faiss_backend.py`. ColBERT uses MaxSim scoring -- normalization not needed.

## Incremental Index Updates

Both backends support incremental updates (only new/changed files re-embedded).
- **FAISS**: reconstructs unchanged vectors via `faiss.reconstruct()`
- **ColBERT**: uses PLAID `add_documents()` for adds. Cannot delete -- full rebuild at >= 20% deletions. Hard rebuild after 50 incremental updates.
