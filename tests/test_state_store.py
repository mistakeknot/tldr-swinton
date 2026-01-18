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
