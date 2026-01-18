from tldr_swinton.vhs_store import Store


def test_vhs_store_defaults_repo_local(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = Store()
    assert store.root == (tmp_path / ".tldrs").resolve()
    assert store.db_path == store.root / "tldrs_state.db"
    assert store.blob_root == store.root / "blobs"
