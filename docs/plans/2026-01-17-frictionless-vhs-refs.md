# Frictionless VHS Refs

**Date:** 2026-01-17
**Status:** Draft
**Priority:** #2 (per Oracle evaluation)
**Expected Impact:** Eliminates VHS adoption friction, enabling default 90%+ token savings for large outputs

## Overview

Make VHS refs the default output for large context responses so agents naturally pass refs instead of pasting blobs. Currently VHS refs require separate tldrs-vhs install, environment variables, and explicit `--output vhs` flag.

### Current State

- `cli.py:35-119` - VHS helper functions exist (`_vhs_put`, `_vhs_get`, `_vhs_available`, `_make_vhs_preview`)
- `cli.py:51-56` - `_vhs_available()` checks for external `tldrs-vhs` CLI
- `cli.py:358-367` - `--output vhs` and `--include` flags exist but are manual
- `output_formats.py:108-120` - `_estimate_tokens()` provides tiktoken-based counting
- `mcp_server.py:194-230` - MCP `context` tool has no VHS support

### Problems

- **Separate install:** Requires `tldrs-vhs` repo cloned and installed
- **Environment variables:** Non-interactive shells need `TLDRS_VHS_CMD` and `TLDRS_VHS_PYTHONPATH`
- **Manual flag:** Agents must explicitly use `--output vhs`
- **No MCP support:** MCP tools return inline context, not refs

## Architecture Decisions

### 1. Vendor VHS Store into tldr-swinton

**Decision:** Copy `tldrs-vhs/src/tldrs_vhs/store.py` into `src/tldr_swinton/vhs_store.py`

**Rationale:**
- VHS store is ~330 LOC pure Python with zero dependencies
- Eliminates external install step
- Eliminates environment variable friction
- Single `pip install tldr-swinton` includes VHS support

### 2. Auto-Switch to VHS Based on Token Threshold

**Decision:** Auto-switch to VHS ref output when response exceeds configurable threshold (default: 2000 tokens)

**Format when auto-switched:**
```
vhs://abc123...
# Summary: Entry get_context depth=2 functions=15 files=8
# Preview:
[first 30 lines / 2KB of output]
```

### 3. MCP First-Class VHS Refs

**Decision:** Add `vhs_ref` field to MCP tool responses when output exceeds threshold

**MCP Response Schema:**
```json
{
  "content": "[inline preview or full output if small]",
  "vhs_ref": "vhs://abc123..." | null,
  "budget_used": 1234,
  "is_truncated": true | false
}
```

### 4. Lazy VHS Store Initialization

**Decision:** Initialize VHS store on first put/get, not on import

**Rationale:**
- Zero overhead for commands that don't use VHS
- Store directory (`~/.tldrs-vhs/`) created only when needed

## Implementation Tasks

### Task 1: Vendor VHS Store

**Files:**
- Create: `src/tldr_swinton/vhs_store.py`
- Test: `tests/test_vhs_store.py`

Copy `/Users/sma/tldrs-vhs/src/tldrs_vhs/store.py` (~330 LOC) with minimal changes:
- Keep default home at `~/.tldrs-vhs/` for compatibility
- Add `__all__` exports
- Keep SQLite metadata schema unchanged

### Task 2: Replace External VHS Calls with Vendored Store

**Files:**
- Modify: `src/tldr_swinton/cli.py`
- Test: `tests/test_cli_vhs.py`

```python
from .vhs_store import Store as VHSStore

_VHS_STORE: VHSStore | None = None

def _get_vhs_store() -> VHSStore:
    global _VHS_STORE
    if _VHS_STORE is None:
        _VHS_STORE = VHSStore()
    return _VHS_STORE

def _vhs_put(text: str) -> str:
    store = _get_vhs_store()
    return store.put(io.BytesIO(text.encode("utf-8")))

def _vhs_available() -> bool:
    return True  # Always available now
```

### Task 3: Add Auto-Switch Threshold Logic

**Files:**
- Modify: `src/tldr_swinton/cli.py`
- Test: `tests/test_cli_auto_vhs.py`

```python
ctx_p.add_argument(
    "--vhs-threshold",
    type=int,
    default=2000,
    help="Auto-switch to VHS ref when output exceeds N tokens (default: 2000, 0=disabled)",
)
```

```python
def _should_auto_vhs(output: str, threshold: int) -> bool:
    if threshold <= 0:
        return False
    from .output_formats import _estimate_tokens
    return _estimate_tokens(output) > threshold
```

### Task 4: Add MCP VHS Support

**Files:**
- Modify: `src/tldr_swinton/mcp_server.py`
- Test: `tests/test_mcp_vhs.py`

```python
@dataclass
class ContextResult:
    content: str
    vhs_ref: str | None
    budget_used: int
    is_truncated: bool
```

Add `include_vhs: list[str] | None` parameter to context tool.

### Task 5: Update Documentation

**Files:**
- Modify: `docs/agent-workflow.md`
- Modify: `AGENTS.md`
- Modify: `.claude-plugin/skills/tldrs-agent-workflow/SKILL.md`
- Modify: `.codex/skills/tldrs-agent-workflow/SKILL.md`

Remove separate tldrs-vhs install instructions, document auto-switch behavior.

### Task 6: Add Comprehensive Eval

**Files:**
- Create: `evals/frictionless_vhs_eval.py`

**Test scenarios:**
1. Auto-switch triggers for large outputs
2. Preview quality (meaningful first 30 lines)
3. Round-trip integrity
4. MCP VHS ref returns
5. Token savings >90%

### Task 7: Backward Compatibility

Keep external tool fallback (deprecated) with warning:
```python
if os.environ.get("TLDRS_VHS_CMD"):
    warnings.warn(
        "TLDRS_VHS_CMD is deprecated. VHS store is now built-in.",
        DeprecationWarning,
    )
```

## Eval Criteria and Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Zero install friction | No separate install | `pip install tldr-swinton` includes VHS |
| Auto-switch rate | >80% of large outputs | Count `vhs://` refs in agent logs |
| Token savings | >90% | `evals/frictionless_vhs_eval.py` |
| Round-trip integrity | 100% | Verify `get(put(x)) == x` |
| No regressions | Pass all evals | `python evals/vhs_eval.py` |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| SQLite locking on concurrent access | Corruption | SQLite handles this; use WAL mode |
| Disk space growth | Store fills up | Auto-GC on startup (max 500MB) |
| Threshold too aggressive | Small outputs use refs | Default 2000 tokens is conservative |
| MCP clients don't support structured returns | Break compatibility | Keep `content` as primary response |

## Migration Plan

1. **Phase 1 (v0.3.0):** Vendor store + auto-switch + CLI support
2. **Phase 2 (v0.3.1):** MCP VHS ref support
3. **Phase 3 (v0.4.0):** Remove external tool fallback

## Critical Files

| File | Purpose |
|------|---------|
| `/Users/sma/tldrs-vhs/src/tldrs_vhs/store.py` | VHS store to vendor (~330 LOC) |
| `src/tldr_swinton/cli.py` | CLI with existing VHS functions (lines 35-119) |
| `src/tldr_swinton/output_formats.py` | `_estimate_tokens()` for threshold |
| `src/tldr_swinton/mcp_server.py` | MCP server needs VHS support |
| `evals/vhs_eval.py` | Pattern for new eval |
