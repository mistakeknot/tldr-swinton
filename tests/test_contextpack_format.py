from tldr_swinton.contextpack_engine import ContextPack, ContextSlice
from tldr_swinton.output_formats import format_context_pack


def test_contextpack_json_format() -> None:
    pack = ContextPack(
        slices=[ContextSlice(id="a.py:hi", signature="def hi()", code=None, lines=None)],
    )
    out = format_context_pack(pack, fmt="json")
    assert "a.py:hi" in out
