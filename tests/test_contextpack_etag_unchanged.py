from pathlib import Path
import json

from tldr_swinton.api import get_symbol_context_pack
from tldr_swinton.output_formats import format_context_pack


def test_symbol_context_pack_etag_unchanged(tmp_path: Path) -> None:
    """Test that unchanged etag returns structured unchanged response."""
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n")
    pack = get_symbol_context_pack(tmp_path, "foo", budget_tokens=200)
    etag = pack["slices"][0]["etag"]

    same_pack = get_symbol_context_pack(tmp_path, "foo", budget_tokens=200, etag=etag)

    # The pack should indicate unchanged
    assert same_pack.get("unchanged") is True
    assert same_pack.get("slices") == []

    # JSON output should be a structured dict (not bare "UNCHANGED" string)
    out = format_context_pack(same_pack, fmt="json")
    parsed = json.loads(out)
    assert parsed.get("unchanged") is True
    assert parsed.get("budget_used") == 0
