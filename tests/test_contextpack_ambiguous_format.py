from tldr_swinton.output_formats import format_context_pack


def test_contextpack_ambiguous_ultracompact_format() -> None:
    pack = {"ambiguous": True, "candidates": ["a.py:dup", "b.py:dup"], "slices": [], "signatures_only": []}
    out = format_context_pack(pack, fmt="ultracompact")
    assert "Ambiguous" in out
