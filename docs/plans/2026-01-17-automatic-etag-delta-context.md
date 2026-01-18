# Automatic ETag/Delta Context

**Date:** 2026-01-17
**Status:** Draft
**Priority:** #1 (per Oracle evaluation)
**Expected Impact:** 2-5× token savings on multi-turn sessions

## Overview

Make delta context the DEFAULT behavior so agents don't re-request unchanged symbols in multi-turn sessions. The primitives already exist (ETags, `UNCHANGED` responses) but there's no session-level caching that makes this automatic.

### Current State

- `contextpack_engine.py:111` - `_compute_etag(signature, code)` computes SHA256 hash
- Each `ContextSlice` has an `etag` field
- `symbolkite.py:517-518` - Single-symbol ETag check returns `"UNCHANGED"`
- `api.py:1007` - `get_symbol_context_pack()` accepts `etag` parameter

### Limitation

- ETag check only works for single-symbol lookups
- No session-level cache to track multiple symbols across turns
- Agents must manually track and pass ETags per symbol
- No batch delta mechanism

## Architecture Decisions

### 1. Where the Cache Lives

**Decision:** File-based session cache in `.tldrs/sessions/<session_id>.json`

**Rationale:**
- Persists across CLI invocations (agents run multiple commands)
- Isolated per session (parallel agents don't interfere)
- Simple JSON format for debugging
- Automatic cleanup via TTL

**Alternative Considered:** In-memory cache via daemon
- Pro: Faster lookups
- Con: Daemon not always running; complexity
- **Rejected** for MVP; can add daemon integration later

### 2. Session Identification

**Decision:** Explicit `--session-id` CLI flag, auto-generated UUID if omitted

**Rationale:**
- Agent frameworks can pass a consistent ID across turns
- Fallback auto-generation for ad-hoc usage
- MCP server can derive session from connection ID

### 3. Cache Format

```json
{
  "session_id": "abc123",
  "created_at": "2026-01-17T10:00:00Z",
  "last_accessed": "2026-01-17T10:05:00Z",
  "etag_cache": {
    "src/api.py:get_context": "sha256hex...",
    "src/cli.py:main": "sha256hex..."
  },
  "stats": {
    "total_requests": 5,
    "cache_hits": 3,
    "cache_misses": 2
  }
}
```

### 4. Return Format for Delta Context

```json
{
  "budget_used": 1200,
  "slices": [
    {"id": "src/api.py:get_context", "signature": "...", "code": "...", "etag": "abc123"}
  ],
  "signatures_only": ["src/utils.py:helper"],
  "unchanged": ["src/cli.py:main", "src/cli.py:parse_args"],
  "cache_stats": {
    "hit_rate": 0.67,
    "hits": 2,
    "misses": 1
  }
}
```

The `unchanged` field lists symbol IDs whose ETags matched, avoiding full content retransmission.

## Implementation Tasks

### Task 1: Add SessionCache class

**Files:**
- Create: `src/tldr_swinton/session_cache.py`
- Test: `tests/test_session_cache.py`

**SessionCache API:**
```python
class SessionCache:
    def __init__(self, project_root: Path, session_id: str | None = None, ttl_seconds: int = 14400)
    def get(self, symbol_id: str) -> str | None
    def set(self, symbol_id: str, etag: str) -> None
    def check_batch(self, symbol_etags: dict[str, str]) -> tuple[set[str], set[str]]  # (unchanged, changed)
    def update_batch(self, symbol_etags: dict[str, str]) -> None
    def hit_rate(self) -> float
    def persist(self) -> None
    @classmethod
    def cleanup_expired(cls, project_root: Path, ttl_seconds: int) -> int
```

### Task 2: Integrate SessionCache into ContextPackEngine

**Files:**
- Modify: `src/tldr_swinton/contextpack_engine.py`
- Test: `tests/test_contextpack_delta.py`

**Add method:**
```python
def build_context_pack_delta(
    self,
    candidates: list[Candidate],
    cache: SessionCache,
    budget_tokens: int | None = None,
) -> ContextPackDelta:
    """Build context pack with delta detection.

    Returns only changed slices; unchanged symbols listed in manifest.
    """
```

### Task 3: Add CLI `--session-id` and `--delta` flags

**Files:**
- Modify: `src/tldr_swinton/cli.py`
- Test: `tests/test_cli_session.py`

**Changes:**
```python
parser.add_argument("--session-id", default=None, help="Session ID for ETag caching")
ctx_p.add_argument("--delta", action="store_true", help="Return only changed slices")
```

### Task 4: Add SymbolKite delta adapter

**Files:**
- Modify: `src/tldr_swinton/engines/symbolkite.py`
- Test: `tests/test_symbolkite_delta.py`

**Add:**
```python
def get_context_pack_delta(
    project: str | Path,
    entry_point: str,
    session_cache: SessionCache,
    depth: int = 2,
    language: str = "python",
    budget_tokens: int | None = None,
) -> dict:
```

### Task 5: Add MCP session support

**Files:**
- Modify: `src/tldr_swinton/mcp_server.py`
- Test: `tests/test_mcp_delta.py`

**Changes:**
- Add `session_id` parameter to `context` tool
- Track session cache per MCP connection
- Return delta format when session_id provided

### Task 6: Add eval for cache hit rate

**Files:**
- Create: `evals/delta_context_eval.py`

**Simulated workflow:**
```
Turn 1: Request context for authenticate()
Turn 2: Request context for validate_token() - overlaps with turn 1
Turn 3: Request context for refresh_token() - overlaps with turns 1-2
Turn 4: Re-request authenticate() after edit - should detect change
Turn 5: Request unchanged symbol - should be 100% cache hit
```

### Task 7: Documentation

**Files:**
- Modify: `docs/agent-workflow.md`
- Modify: `AGENTS.md`
- Modify: `.claude-plugin/skills/tldrs-agent-workflow/SKILL.md`
- Modify: `.codex/skills/tldrs-agent-workflow/SKILL.md`

## Eval Criteria and Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Cache hit rate | >60% | `evals/delta_context_eval.py` multi-turn workflow |
| Token savings | 2-5× over baseline | Compare delta vs full context in 5-turn session |
| Latency overhead | <50ms | ETag lookup should be O(1) hash comparison |
| No regressions | Pass all existing evals | `evals/agent_workflow_eval.py` must still pass |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cache corruption | Stale ETags returned | TTL-based expiry; cache reset on error |
| Large cache files | Disk usage | Limit to ~10K symbols; LRU eviction |
| Session ID collision | Cross-session pollution | UUID generation; project-scoped paths |
| Daemon not running | Cache not persisted | File-based cache works without daemon |
| Breaking API changes | Downstream tools fail | Backward-compatible: delta mode is opt-in |

## Migration Plan

1. **Phase 1 (MVP):** CLI support with `--session-id --delta`
2. **Phase 2:** MCP server integration
3. **Phase 3:** Daemon integration for faster lookups
4. **Phase 4:** Auto-session detection (e.g., from TTY/PTY ID)

## Critical Files

| File | Purpose |
|------|---------|
| `src/tldr_swinton/contextpack_engine.py` | Core engine; add `build_context_pack_delta()` |
| `src/tldr_swinton/engines/symbolkite.py` | SymbolKite adapter; add delta-aware wrapper |
| `src/tldr_swinton/cli.py` | CLI; add `--session-id` and `--delta` flags |
| `src/tldr_swinton/mcp_server.py` | MCP server; add session tracking |
| `evals/agent_workflow_eval.py` | Pattern to follow for new eval |
