"""Schema-aware JSON compression for ContextPack output."""
from __future__ import annotations

from typing import Any


ALIASES = {
    "id": "i",
    "signature": "g",
    "code": "c",
    "lines": "l",
    "relevance": "r",
    "meta": "m",
    "etag": "e",
    "file": "f",
    "type": "t",
}
REVERSE_ALIASES = {v: k for k, v in ALIASES.items()}

_COLUMN_NAMES = {
    "id": "ids",
    "signature": "signatures",
    "code": "code",
    "lines": "lines",
    "relevance": "relevance",
    "meta": "meta",
    "etag": "etags",
    "file": "files",
    "type": "types",
}
_REVERSE_COLUMN_NAMES = {v: k for k, v in _COLUMN_NAMES.items()}


def _map_keys(data: Any, aliases: dict[str, str]) -> Any:
    if isinstance(data, dict):
        return {_map_key(key, aliases): _map_keys(value, aliases) for key, value in data.items()}
    if isinstance(data, list):
        return [_map_keys(item, aliases) for item in data]
    return data


def _map_key(key: Any, aliases: dict[str, str]) -> Any:
    if isinstance(key, str):
        return aliases.get(key, key)
    return key


def pack_json(data: dict, aliases: dict = ALIASES) -> dict:
    return _map_keys(data, aliases)


def unpack_json(packed: dict, aliases: dict = REVERSE_ALIASES) -> dict:
    return _map_keys(packed, aliases)


def to_columnar(slices: list[dict]) -> dict:
    if not slices:
        return {}

    ordered_keys: list[str] = []
    seen: set[str] = set()
    for row in slices:
        if not isinstance(row, dict):
            continue
        for key in row:
            if key not in seen:
                seen.add(key)
                ordered_keys.append(key)

    columns: dict[str, list[Any]] = {}
    for key in ordered_keys:
        values = [row.get(key) if isinstance(row, dict) else None for row in slices]
        if any(value is not None for value in values):
            column_name = _COLUMN_NAMES.get(key, key)
            columns[column_name] = values
    return columns


def from_columnar(columnar: dict) -> list[dict]:
    if not columnar:
        return []

    list_columns = [
        (column_name, values)
        for column_name, values in columnar.items()
        if isinstance(values, list)
    ]
    if not list_columns:
        return []

    row_count = max((len(values) for _, values in list_columns), default=0)
    rows: list[dict] = [{} for _ in range(row_count)]

    for column_name, values in list_columns:
        key = _REVERSE_COLUMN_NAMES.get(column_name, column_name)
        for index in range(row_count):
            value = values[index] if index < len(values) else None
            if value is not None:
                rows[index][key] = value
    return rows


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _elide(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            cleaned = _elide(item)
            if not _is_empty(cleaned):
                result[key] = cleaned
        return result
    if isinstance(value, list):
        result_list = []
        for item in value:
            cleaned = _elide(item)
            if not _is_empty(cleaned):
                result_list.append(cleaned)
        return result_list
    return value


def elide_nulls(data: dict) -> dict:
    return _elide(data)
