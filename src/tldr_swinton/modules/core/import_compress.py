"""Import graph compression and deduplication for ContextPack output."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import re


_FROM_IMPORT_RE = re.compile(r"^from\s+([^\s]+)\s+import\s+(.+)$")
_TS_NAMED_RE = re.compile(r"^import\s*\{([^}]+)\}\s*from\s*[\"']([^\"']+)[\"']")
_TS_DEFAULT_RE = re.compile(r"^import\s+([^\s{][^\s]*)\s+from\s*[\"']([^\"']+)[\"']")
_PLAIN_IMPORT_RE = re.compile(r"^import\s+(.+)$")


@dataclass
class ImportFrequencyIndex:
    """Tracks import frequency across files in a context pack."""

    # (module, name) -> count of files containing this import
    frequencies: Counter = field(default_factory=Counter)
    total_files: int = 0

    @classmethod
    def build(cls, file_imports: dict[str, list[str]]) -> "ImportFrequencyIndex":
        """Build index from {file_path: [import_strings]} mapping."""
        index = cls(total_files=len(file_imports))
        for imports in file_imports.values():
            per_file_pairs = set(_extract_pairs(imports))
            index.frequencies.update(per_file_pairs)
        return index

    def get_ubiquitous(self, threshold: float = 0.5) -> set[str]:
        """Return imports appearing in >threshold fraction of files."""
        if self.total_files <= 0:
            return set()
        return {
            _pair_to_import(module, name)
            for (module, name), count in self.frequencies.items()
            if (count / self.total_files) > threshold
        }

    def get_unique_imports(self, file_path: str, imports: list[str]) -> list[str]:
        """Return imports unique to this file (not in ubiquitous set)."""
        _ = file_path
        ubiquitous = self.get_ubiquitous()
        unique: list[str] = []
        seen: set[str] = set()
        for module, name in _extract_pairs(imports):
            key = _pair_to_import(module, name)
            if key in ubiquitous or key in seen:
                continue
            seen.add(key)
            unique.append(key)
        return unique


def format_common_imports(common: set[str]) -> str:
    """Format common imports grouped by source module on one line."""
    plain, named = _group_by_module(common)
    parts: list[str] = []

    for module in sorted(plain):
        parts.append(module)

    for module in sorted(named):
        names = sorted(named[module])
        if len(names) == 1:
            parts.append(f"{module}: {names[0]}")
        else:
            parts.append(f"{module}: {{{', '.join(names)}}}")

    return ", ".join(parts)


def format_unique_imports(unique: list[str]) -> str:
    """Format per-file unique imports grouped by source module."""
    plain, named = _group_by_module(unique)
    lines: list[str] = []

    for module in sorted(plain):
        lines.append(module)

    for module in sorted(named):
        names = sorted(named[module])
        if len(names) == 1:
            lines.append(f"{module}: {names[0]}")
        else:
            lines.append(f"{module}: {{{', '.join(names)}}}")

    return "\n".join(lines)


def compress_imports_section(
    file_imports: dict[str, list[str]], threshold: float = 0.5
) -> tuple[str, dict[str, str]]:
    """Split imports into a common header and per-file unique groups."""
    index = ImportFrequencyIndex.build(file_imports)
    common = index.get_ubiquitous(threshold=threshold)
    common_line = format_common_imports(common)

    common_header = ""
    if common_line:
        common_header = "## Common Imports\n" + common_line

    per_file: dict[str, str] = {}
    for file_path, imports in file_imports.items():
        unique = index.get_unique_imports(file_path, imports)
        per_file[file_path] = format_unique_imports(unique)

    return common_header, per_file


def _extract_pairs(imports: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in imports:
        pairs.extend(_parse_import(raw))
    return pairs


def _parse_import(raw: str) -> list[tuple[str, str]]:
    text = raw.strip()
    if not text:
        return []

    from_match = _FROM_IMPORT_RE.match(text)
    if from_match:
        module = from_match.group(1).strip()
        names_part = from_match.group(2).strip().strip("()")
        names = [_clean_name(part) for part in names_part.split(",")]
        return [(module, name) for name in names if name]

    ts_named = _TS_NAMED_RE.match(text)
    if ts_named:
        module = ts_named.group(2).strip()
        names = [_clean_name(part) for part in ts_named.group(1).split(",")]
        return [(module, name) for name in names if name]

    ts_default = _TS_DEFAULT_RE.match(text)
    if ts_default:
        name = _clean_name(ts_default.group(1))
        module = ts_default.group(2).strip()
        return [(module, name)] if name else [(module, "")]

    plain = _PLAIN_IMPORT_RE.match(text)
    if plain:
        names = [_clean_name(part) for part in plain.group(1).split(",")]
        return [(name, "") for name in names if name]

    return []


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return ""
    if " as " in cleaned:
        cleaned = cleaned.split(" as ", 1)[0].strip()
    return cleaned


def _pair_to_import(module: str, name: str) -> str:
    if name:
        return f"from {module} import {name}"
    return f"import {module}"


def _group_by_module(imports: set[str] | list[str]) -> tuple[set[str], dict[str, set[str]]]:
    plain: set[str] = set()
    named: dict[str, set[str]] = defaultdict(set)

    for import_stmt in imports:
        for module, name in _parse_import(import_stmt):
            if name:
                named[module].add(name)
            else:
                plain.add(module)

    return plain, named
