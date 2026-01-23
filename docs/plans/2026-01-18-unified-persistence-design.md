# Unified Persistence (Repo-Local State + VHS)

**Date:** 2026-01-18
**Status:** ✅ Implemented (2026-01-22)
**Owner:** tldr-swinton

## Goal
Create a single repo-local persistence layer that stores:
- VHS blob metadata (content-addressed)
- Session/delivery records for ETag/delta context
- GC metadata and stats

This must support large payloads efficiently and avoid cross-repo leakage.

## Scope
- Repo-local storage under `.tldrs/`
- One SQLite file: `.tldrs/tldrs_state.db`
- File-backed blobs under `.tldrs/blobs/` (streaming-friendly)
- APIs for VHS put/get/has/info + session/delivery bookkeeping

## Non-Goals
- Global shared cache by default
- Cross-repo deduplication
- Full session replay or analytics dashboards

## Storage Layout
```
.tldrs/
  tldrs_state.db
  blobs/
    <hh>/<hh>/<sha256>
  tmp/
```

- `vhs://<sha256>` remains the canonical ref.
- Blobs are stored as files for efficient streaming; SQLite stores metadata only.

## Schema (SQLite)

### objects (VHS metadata)
```
objects(
  hash TEXT PRIMARY KEY,
  size INTEGER NOT NULL,
  stored_size INTEGER NOT NULL DEFAULT 0,
  compression TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  last_accessed TEXT NOT NULL
)
```

### sessions
```
sessions(
  session_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  last_accessed TEXT NOT NULL,
  repo_fingerprint TEXT NOT NULL,
  default_language TEXT
)
```

### deliveries (ETag/session cache)
```
deliveries(
  session_id TEXT NOT NULL,
  symbol_id TEXT NOT NULL,
  etag TEXT NOT NULL,
  representation TEXT NOT NULL,    -- full | signature_only | pdg_slice | vhs_ref
  vhs_ref TEXT,
  token_estimate INTEGER,
  last_accessed TEXT NOT NULL,
  PRIMARY KEY(session_id, symbol_id)
)
```

Indexes:
- `deliveries(session_id, symbol_id)` (PK)
- `deliveries(last_accessed)`
- `objects(last_accessed)`

## Key Decisions
1. **Repo-local by default**: `.tldrs/` avoids cross-repo leakage and simplifies GC.
2. **File-backed blobs**: Keep streaming and large payloads fast; DB stays small.
3. **Single DB file**: `tldrs_state.db` unifies VHS + sessions + deliveries.
4. **Representation-aware delta**: Only mark as `UNCHANGED` if previously sent as `full` or `vhs_ref`.

## API Surface (Proposed)
`vhs_store.py` (vendored store + extensions):
- `put(stream, compress=False, compress_min_bytes=None) -> vhs://...`
- `get(ref, out=None)`
- `has(ref) -> bool`
- `info(ref) -> ObjectInfo | None`
- `stats() -> dict`
- `gc(max_age_days, max_size_mb, dry_run=False, keep_last=0) -> dict`

`state_store.py` (new wrapper):
- `open_session(session_id, repo_fingerprint, default_language=None)`
- `record_delivery(session_id, symbol_id, etag, representation, vhs_ref=None, token_estimate=None)`
- `get_delivery(session_id, symbol_id) -> Delivery | None`
- `touch_session(session_id)`
- `cleanup_expired(ttl_seconds) -> dict`

## Delta Behavior
- Delta checks use `(session_id, symbol_id)` deliveries.
- If ETag matches and representation is `full` or `vhs_ref`, return signature-only slice and list under `unchanged`.
- If representation is `signature_only`, treat as changed/unknown.
- If omitted due to budget, still record representation and ETag for later hits.

## GC Policy
- `objects`: delete by TTL and/or size cap using `last_accessed`.
- `sessions/deliveries`: prune by `last_accessed` TTL; remove deliveries for dead sessions.
- GC is repo-local; no cross-repo coordination needed.

## Migration Plan
1. Vendor `tldrs-vhs` store into `src/tldr_swinton/vhs_store.py`.
2. Change default root to `.tldrs/` and DB filename to `tldrs_state.db`.
3. Add `sessions` and `deliveries` tables on init.
4. Add `state_store.py` wrapper and wire CLI/MCP.

## Testing
- `tests/test_vhs_store.py`: put/get/has/info, compression path.
- `tests/test_state_store.py`: session open, delivery record, delta hit/miss.
- `tests/test_gc.py`: TTL pruning for objects + deliveries.

## Risks & Mitigations
- **SQLite lock contention**: use WAL + short-lived connections.
- **False UNCHANGED**: representation-aware delta (only full/vhs_ref).
- **Repo fingerprint drift**: store repo fingerprint in sessions and warn on mismatch.

## Defaults (Resolved)
- **Compression**: `compress_min_bytes = 64 * 1024` (64 KB). Use compression only when size >= threshold.
- **Token estimate**: heuristic `len(text) // 4` (fallback if tiktoken not installed). Optional tiktoken integration later.
- **Repo fingerprint**: `sha256(git_root + HEAD_commit + branch_name)` with fallback to `sha256(git_root + .git/index mtime)` when detached/dirty.
