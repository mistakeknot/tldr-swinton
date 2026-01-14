from pathlib import Path

from tldr_swinton.tldrsignore import ensure_tldrsignore


def test_ensure_tldrsignore_migrates_legacy(tmp_path: Path) -> None:
    legacy = tmp_path / ".tldrignore"
    legacy.write_text("vendor/\n")

    created, message = ensure_tldrsignore(tmp_path)

    assert created is True
    assert ".tldrsignore" in message
    assert "Migrated" in message
    new_path = tmp_path / ".tldrsignore"
    assert new_path.exists()
    assert new_path.read_text() == legacy.read_text()
