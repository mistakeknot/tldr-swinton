from pathlib import Path
import json

from tldr_swinton.api import get_symbol_context_pack
from tldr_swinton.output_formats import format_context_pack


def test_symbol_context_pack_etag_unchanged(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n")
    pack = get_symbol_context_pack(tmp_path, "foo", budget_tokens=200)
    etag = pack["slices"][0]["etag"]

    same_pack = get_symbol_context_pack(tmp_path, "foo", budget_tokens=200, etag=etag)
    out = format_context_pack(same_pack, fmt="json")
    assert json.loads(out) == "UNCHANGED"
