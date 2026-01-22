# Automatic ETag/Delta Context

**Date:** 2026-01-17
**Status:** ✅ Implemented (2026-01-22)
**Priority:** #1 (per Oracle evaluation)
**Expected Impact:** ~60% token savings on multi-turn sessions (measured: 63.4%)

## Implementation Notes (2026-01-22)

Delta context is implemented for `diff-context` command which includes full code bodies.
The standard `context` command returns signatures-only by design (95% savings already),
so delta mode there only adds `[UNCHANGED]` markers without reducing output size.

**Key insight:** Delta mode provides real savings when there's code to omit. Use
`tldrs diff-context --session-id <id>` for multi-turn workflows.

**Measured results on real codebase:**
- First call: 55KB (134 symbols with code)
- Second call: 20KB (all unchanged, code omitted)
- Savings: 63.4%

## Overview

Make delta context the DEFAULT behavior for CLI/MCP so agents don't re-request unchanged symbols in multi-turn sessions, while keeping API/library delta opt-in for compatibility. The primitives already exist (ETags, `UNCHANGED` responses) but there's no session-level caching that makes this automatic.

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

**Decision:** Hybrid session ID (repo-default + override via `--session-id` or env)

**Rationale:**
- Stable default enables delta caching across CLI invocations without extra agent plumbing
- Agent frameworks can still pass a consistent ID across turns
- Overrides available via `--session-id` or `TLDRS_SESSION_ID`
- MCP server can derive session from connection ID or explicit `session_id`

**Repo default:**
- Store a default ID in `.tldrs/session_id` (created on first use)
- CLI uses this when no explicit session ID is provided

### 3. Cache Format

```json
{
  "session_id": "abc123",
  "created_at": "2026-01-17T10:00:00Z",
  "last_accessed": "2026-01-17T10:05:00Z",
  "max_entries": 10000,
  "etag_cache": {
    "src/api.py:get_context": {
      "etag": "sha256hex...",
      "last_accessed": "2026-01-17T10:05:00Z"
    },
    "src/cli.py:main": {
      "etag": "sha256hex...",
      "last_accessed": "2026-01-17T10:05:00Z"
    }
  },
  "stats": {
    "total_requests": 5,
    "cache_hits": 3,
    "cache_misses": 2
  }
}
```

`etag_cache` keys use canonical symbol IDs (normalized path + fully-qualified symbol + language).

### 4. Return Format for Delta Context (Delta Response Type)

```json
{
  "budget_used": 1200,
  "slices": [
    {"id": "src/api.py:get_context", "signature": "...", "code": "...", "etag": "abc123"}
  ],
  "slices": [
    {"id": "src/utils.py:helper", "signature": "def helper(...)", "code": null, "lines": null},
    {"id": "src/cli.py:main", "signature": "def main(...)", "code": null, "lines": null},
    {"id": "src/cli.py:parse_args", "signature": "def parse_args(...)", "code": null, "lines": null}
  ],
  "unchanged": ["src/cli.py:main", "src/cli.py:parse_args"],
  "cache_stats": {
    "hit_rate": 0.67,
    "hits": 2,
    "misses": 1
  }
}
```

Delta responses include signature-only slices by setting `code: null` on those slices (unchanged symbols and truncated-by-budget symbols). `unchanged` is a subset of the signature-only set. Code is omitted for unchanged symbols to preserve token savings while keeping agent structure/context intact.
`hit_rate` is per-session cumulative: `hits / (hits + misses)` for the current session cache.

### 5. Canonical Symbol IDs

**Decision:** Canonical, normalized symbol IDs (normalized path + fully-qualified symbol + language).

**Rationale:**
- Stable IDs improve cache hit rate across commands and surfaces
- Avoids ambiguous/duplicate entries for overloaded or aliased symbols
- Keeps cache keys consistent for mixed-language repos

**Spec (MVP):**
- Normalize file path to repo-relative, POSIX-style
- Prefix the existing symbol ID with normalized path + language

## Implementation Tasks

### Task 1: Add SessionCache class

**Files:**
- Create: `src/tldr_swinton/session_cache.py`
- Test: `tests/test_session_cache.py`

**SessionCache API:**
```python
class SessionCache:
    def __init__(self, project_root: Path, session_id: str | None = None, ttl_seconds: int = 14400, max_entries: int = 10000)
    def get(self, symbol_id: str) -> str | None
    def set(self, symbol_id: str, etag: str) -> None
    def check_batch(self, symbol_etags: dict[str, str]) -> tuple[set[str], set[str]]  # (unchanged, changed)
    def update_batch(self, symbol_etags: dict[str, str]) -> None
    def hit_rate(self) -> float
    def persist(self) -> None
    @classmethod
    def cleanup_expired(cls, project_root: Path, ttl_seconds: int) -> int
```

**Storage notes:**
- Persist to `.tldrs/sessions/<session_id>.json`
- Use file lock + atomic write (write temp, fsync, rename)
- Track per-symbol `last_accessed` for LRU eviction when `max_entries` exceeded

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

**Notes:**
- Normalize symbol IDs (canonical format) before cache lookup
- Mark unchanged symbols with `code: null` (signature-only)

### Task 3: Add API delta entrypoint

**Files:**
- Modify: `src/tldr_swinton/api.py`
- Test: `tests/test_api_delta.py`

**Add:**
```python
def get_symbol_context_pack_delta(
    project: str | Path,
    entry_point: str,
    session_cache: SessionCache,
    depth: int = 2,
    language: str = "python",
    budget_tokens: int | None = None,
) -> dict:
```

### Task 4: Add CLI `--session-id` and `--no-delta` flags

**Files:**
- Modify: `src/tldr_swinton/cli.py`
- Test: `tests/test_cli_session.py`

**Changes:**
```python
parser.add_argument("--session-id", default=None, help="Session ID for ETag caching")
ctx_p.add_argument("--no-delta", action="store_true", help="Disable delta for CLI/MCP default")
```

**Default behavior:**
- CLI/MCP default to delta response unless `--no-delta` is set
- API/library exposes delta via an explicit flag/parameter

### Task 5: Add SymbolKite delta adapter

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

### Task 6: Add MCP session support

**Files:**
- Modify: `src/tldr_swinton/mcp_server.py`
- Test: `tests/test_mcp_delta.py`

**Changes:**
- Add `session_id` parameter to `context` tool
- Add `no_delta` boolean parameter to opt out per call
- Track session cache per MCP connection
- Default to delta format for MCP contexts (allow opt-out via `no_delta`)

### Task 7: Add eval for cache hit rate

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

### Task 8: Documentation

**Files:**
- Modify: `docs/agent-workflow.md`
- Modify: `AGENTS.md`
- Modify: `.claude-plugin/skills/tldrs-agent-workflow/SKILL.md`
- Modify: `.codex/skills/tldrs-agent-workflow/SKILL.md`
- Modify: `.gitignore` to include `.tldrs/`

## Eval Criteria and Success Metrics

| Metric | Target | Actual | Measurement |
|--------|--------|--------|-------------|
| Cache hit rate | >60% | 100% (when unchanged) | `tests/test_cli_context_delta.py` |
| Token savings | 2-5× over baseline | ~60% (1.6×) | Real codebase test: 55KB→20KB |
| Latency overhead | <50ms | Negligible | SQLite lookup is O(1) |
| No regressions | Pass all existing evals | ✅ 98 tests pass | `pytest tests/` |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cache corruption | Stale ETags returned | TTL-based expiry; cache reset on error |
| Concurrent writes | Corrupted JSON | File locks + atomic write |
| Large cache files | Disk usage | Limit to ~10K symbols with LRU eviction + TTL |
| Session ID collision | Cross-session pollution | UUID generation; project-scoped paths |
| Daemon not running | Cache not persisted | File-based cache works without daemon |
| Breaking API changes | Downstream tools fail | Backward-compatible: delta mode is opt-in for API/library; CLI/MCP allow `--no-delta` |

## Migration Plan

1. **Phase 1 (MVP):** CLI/MCP default delta with `--no-delta` opt-out + session ID plumbing
2. **Phase 2:** API delta entrypoint + MCP server integration
3. **Phase 3:** Daemon integration for faster lookups
4. **Phase 4:** Auto-session detection (e.g., from TTY/PTY ID)

## Critical Files

| File | Purpose |
|------|---------|
| `src/tldr_swinton/contextpack_engine.py` | Core engine; add `build_context_pack_delta()` |
| `src/tldr_swinton/engines/symbolkite.py` | SymbolKite adapter; add delta-aware wrapper |
| `src/tldr_swinton/cli.py` | CLI; add `--session-id` and `--delta` flags |
| `src/tldr_swinton/api.py` | API delta entrypoint |
| `src/tldr_swinton/mcp_server.py` | MCP server; add session tracking |
| `src/tldr_swinton/session_cache.py` | Session cache implementation |
| `evals/agent_workflow_eval.py` | Pattern to follow for new eval |
