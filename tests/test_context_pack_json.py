import json

from tldr_swinton.output_formats import format_context_pack


def test_context_pack_json_is_compact() -> None:
    pack = {"base": "BASE", "head": "HEAD", "slices": [{"id": "a.py:foo"}]}
    output = format_context_pack(pack, fmt="json")
    assert output == json.dumps(pack, separators=(",", ":"), ensure_ascii=False)


def test_context_pack_json_pretty_is_indented() -> None:
    pack = {"base": "BASE", "head": "HEAD", "slices": [{"id": "a.py:foo"}]}
    output = format_context_pack(pack, fmt="json-pretty")
    assert output == json.dumps(pack, indent=2, ensure_ascii=False)
