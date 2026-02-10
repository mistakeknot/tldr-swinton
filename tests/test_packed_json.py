import json

from tldr_swinton.modules.core.json_codec import (
    elide_nulls,
    from_columnar,
    pack_json,
    to_columnar,
    unpack_json,
)
from tldr_swinton.output_formats import format_context_pack


def _make_pack(slice_count: int = 20) -> dict:
    file_path = "src/very/long/path/module.py"
    slices = []
    for i in range(slice_count):
        slices.append(
            {
                "id": f"{file_path}:function_{i}",
                "signature": f"def function_{i}(arg: int) -> int",
                "code": "line1\nline2\nline3",
                "lines": [i * 10 + 1, i * 10 + 5],
                "relevance": "contains_diff" if i % 2 == 0 else "caller_of_diff",
                "meta": {"file": file_path, "type": "function"},
                "etag": f"etag-{i}",
            }
        )
    return {
        "budget_used": 1200,
        "base": "BASE",
        "head": "HEAD",
        "slices": slices,
        "unchanged": [f"{file_path}:function_0", f"{file_path}:function_1"],
    }


def test_pack_unpack_roundtrip() -> None:
    data = {
        "id": "a.py:foo",
        "signature": "def foo()",
        "code": "return 1",
        "meta": {"etag": "abc", "type": "function"},
        "lines": [1, 3],
        "nested": [{"relevance": "contains_diff"}],
    }
    packed = pack_json(data)
    unpacked = unpack_json(packed)
    assert unpacked == data


def test_columnar_roundtrip() -> None:
    slices = [
        {
            "id": "a.py:foo",
            "signature": "def foo()",
            "code": "return 1",
            "lines": [1, 3],
            "relevance": "contains_diff",
            "etag": "e1",
        },
        {
            "id": "b.py:bar",
            "signature": "def bar()",
            "code": "return 2",
            "lines": [4, 6],
            "relevance": "caller_of_diff",
            "etag": "e2",
        },
    ]
    columnar = to_columnar(slices)
    restored = from_columnar(columnar)
    assert restored == slices


def test_key_aliasing() -> None:
    packed = pack_json(
        {
            "signature": "def foo()",
            "code": "return 1",
            "meta": {"etag": "abc", "type": "function"},
        }
    )
    assert "g" in packed
    assert "c" in packed
    assert "m" in packed
    assert packed["m"]["e"] == "abc"
    assert packed["m"]["t"] == "function"


def test_null_elision() -> None:
    data = {
        "id": "a.py:foo",
        "code": None,
        "lines": [],
        "meta": {"etag": None, "type": "function", "note": ""},
        "count": 0,
        "flag": False,
        "nested": [None, {}, "", {"ok": "yes"}],
    }
    elided = elide_nulls(data)
    assert "code" not in elided
    assert "lines" not in elided
    assert elided["meta"] == {"type": "function"}
    assert elided["count"] == 0
    assert elided["flag"] is False
    assert elided["nested"] == [{"ok": "yes"}]


def test_packed_json_format_smaller() -> None:
    pack = _make_pack()
    json_output = format_context_pack(pack, fmt="json")
    packed_output = format_context_pack(pack, fmt="packed-json")
    assert len(packed_output) < len(json_output)


def test_columnar_json_format_smaller() -> None:
    pack = _make_pack()
    packed_output = format_context_pack(pack, fmt="packed-json")
    columnar_output = format_context_pack(pack, fmt="columnar-json")
    assert len(columnar_output) < len(packed_output)


def test_format_context_pack_packed_json() -> None:
    pack = _make_pack(slice_count=3)
    output = format_context_pack(pack, fmt="packed-json")
    parsed = json.loads(output)
    assert isinstance(parsed, dict)
    assert "_aliases" in parsed
    assert "_paths" in parsed
    assert "slices" in parsed


def test_format_context_pack_columnar_json() -> None:
    pack = _make_pack(slice_count=3)
    output = format_context_pack(pack, fmt="columnar-json")
    parsed = json.loads(output)
    assert isinstance(parsed, dict)
    assert "_schema" in parsed
    assert isinstance(parsed["slices"], dict)
    assert parsed["_schema"] == list(parsed["slices"].keys())
