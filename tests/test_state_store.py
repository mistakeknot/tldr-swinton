from datetime import datetime, timedelta, timezone

from tldr_swinton.state_store import StateStore


def test_state_store_records_delivery(tmp_path):
    project_root = tmp_path
    store = StateStore(project_root)
    store.open_session("s1", repo_fingerprint="abc")
    store.record_delivery(
        session_id="s1",
        symbol_id="src/app.py:main",
        etag="etag123",
        representation="full",
        vhs_ref="vhs://deadbeef" + "0" * 56,
        token_estimate=42,
    )
    delivery = store.get_delivery("s1", "src/app.py:main")
    assert delivery is not None
    assert delivery["etag"] == "etag123"
    assert delivery["representation"] == "full"


def test_state_store_cleanup_removes_old_entries(tmp_path):
    store = StateStore(tmp_path)
    store.open_session("s1", repo_fingerprint="abc")
    store.record_delivery("s1", "sym", "etag", "full")

    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with store._conn() as conn:
        conn.execute("UPDATE sessions SET last_accessed = ?", (old,))
        conn.execute("UPDATE deliveries SET last_accessed = ?", (old,))

    removed = store.cleanup_expired(ttl_seconds=60)
    assert removed["sessions"] == 1
    assert removed["deliveries"] == 1
