from pathlib import Path

from tldr_bench.variants.helpers import format_json, parse_entry


def test_parse_entry_resolves_path(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "foo.py"
    file_path.write_text("print('hi')", encoding="utf-8")

    task = {"entry": "foo.py:hello", "repo": str(repo)}
    resolved_path, func_name = parse_entry(task)

    assert resolved_path == file_path
    assert func_name == "hello"


def test_format_json_compact_and_pretty():
    data = {"a": 1, "b": 2}
    compact = format_json(data, "json")
    pretty = format_json(data, "json-pretty")

    assert compact == '{"a":1,"b":2}'
    assert "\n" in pretty
