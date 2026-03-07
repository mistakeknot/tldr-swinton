# Key Data Structures

**FunctionInfo** (`modules/core/ast_extractor.py`):
```python
@dataclass
class FunctionInfo:
    name: str; params: list[str]; return_type: str | None
    docstring: str | None; is_method: bool = False; is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    line_number: int = 0; language: str = "python"
```

**ModuleInfo** (`modules/core/ast_extractor.py`): Container for file analysis results.

**CodeUnit** (`modules/semantic/backend.py`): Minimal metadata for search results (id, name, file, line, unit_type, signature, file_hash).

## Delta Context Mode

Delta mode tracks delivered symbols per session and skips re-sending unchanged code. Provides ~60% savings in multi-turn conversations **when code is unchanged**.

- Works best with `diff-context` (full code bodies). Less useful with `context` (already signatures-only).
- Usage: `--session-id <id>` or `--delta` flag. Auto-generate: `--session-id auto`.
- State stored in `.tldrs/state.sqlite3`. Sessions expire after 24h inactivity.

**Caveat**: Delta savings collapse to near-zero if code changes between calls. Most valuable for iterative Q&A, not active editing.

## Compression Modes

`diff-context --compress` supports:
- **`two-stage`**: Indent-aware block detection + knapsack DP. Saves 35-73% tokens.
- **`chunk-summary`**: LLM-ready summaries replacing code. Saves 85-95% but loses detail.

See `docs/dev-reference.md` for promotion gate criteria.

## Output Caps

`context`, `diff-context`, and `slice` support `--max-lines` and `--max-bytes` post-format truncation:
```bash
tldrs context main --project . --max-lines=20
tldrs diff-context --project . --max-bytes=4096
```
Truncated output gets a `[TRUNCATED: ...]` marker. JSON output remains valid with `"truncated": true`.
