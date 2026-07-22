from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
_SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".tldrs",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "vendor",
}
_STOPWORDS = {
    "after",
    "also",
    "before",
    "behavior",
    "code",
    "does",
    "expected",
    "file",
    "from",
    "have",
    "into",
    "make",
    "must",
    "only",
    "preserve",
    "recent",
    "reports",
    "restore",
    "return",
    "same",
    "should",
    "still",
    "task",
    "that",
    "their",
    "this",
    "uses",
    "using",
    "when",
    "while",
    "with",
}
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|[0-9]+")
_EXPLICIT_PATH = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+)"
)


@dataclass(frozen=True)
class ReconExcerpt:
    path: str
    start_line: int
    end_line: int
    score: float
    text: str


def _canonical_term(value: str) -> str | None:
    term = value.lower()
    if len(term) < 3 or term in _STOPWORDS:
        return None
    if term.startswith("call"):
        return "call"
    if term.startswith("dedup") or term.startswith("duplic"):
        return "dedup"
    if term.startswith("repeat"):
        return "dedup"
    if term.startswith(("add", "append", "insert")):
        return "insert"
    if term.startswith(("observ", "record")):
        return "record"
    if term.startswith("match"):
        return "match"
    if term.startswith("truncat"):
        return "truncate"
    for suffix in ("ization", "ation", "ition", "ments", "ment", "ingly", "edly"):
        if term.endswith(suffix) and len(term) > len(suffix) + 3:
            term = term[: -len(suffix)]
            break
    for suffix in ("ing", "ed", "ly", "es", "s"):
        if term.endswith(suffix) and len(term) > len(suffix) + 3:
            term = term[: -len(suffix)]
            break
    return term if term not in _STOPWORDS and len(term) >= 3 else None


def _terms(text: str) -> tuple[str, ...]:
    terms: list[str] = []
    for raw in _WORD.findall(text):
        parts = raw.replace("_", " ").split()
        for part in parts:
            camel_parts = _CAMEL.findall(part) or [part]
            for camel_part in camel_parts:
                canonical = _canonical_term(camel_part)
                if canonical is not None:
                    terms.append(canonical)
    return tuple(terms)


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in _SKIP_PARTS for part in relative.parts):
            continue
        try:
            if path.stat().st_size > 250_000:
                continue
        except OSError:
            continue
        files.append(path)
    return sorted(files)


def _best_window(
    lines: list[str],
    query_terms: set[str],
    idf: dict[str, float],
    *,
    radius: int = 12,
) -> tuple[int, int, float]:
    if not lines:
        return (0, 0, 0.0)
    line_terms = [set(_terms(line)) & query_terms for line in lines]
    best_index = max(
        range(len(lines)),
        key=lambda index: sum(
            idf[term]
            for term in set().union(
                *line_terms[max(0, index - radius) : index + radius + 1]
            )
        ),
    )
    start = max(0, best_index - radius)
    end = min(len(lines), best_index + radius + 1)
    covered = set().union(*line_terms[start:end])
    return (start, end, sum(idf[term] for term in covered))


def _suspicious_guard_line(lines: list[str], query: set[str]) -> int | None:
    if "dedup" not in query and "insert" not in query:
        return None
    guard = re.compile(r"\bif\s+(?P<item>[A-Za-z_][A-Za-z0-9_]*)\s+in\s+.+:")
    for index, line in enumerate(lines):
        match = guard.search(line)
        if match is None:
            continue
        item = match.group("item")
        following = "\n".join(lines[index + 1 : index + 4])
        if re.search(rf"\.append\(\s*{re.escape(item)}\s*\)", following):
            return index
    return None


def rank_source_excerpts(
    root: Path,
    prompt: str,
    *,
    max_files: int = 3,
    max_chars: int = 6_000,
) -> tuple[ReconExcerpt, ...]:
    query = set(_terms(prompt))
    if not query or max_files <= 0 or max_chars <= 0:
        return ()

    documents: list[tuple[Path, str, Counter[str]]] = []
    document_frequency: Counter[str] = Counter()
    for path in _source_files(root):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        counts = Counter(_terms(text))
        relative = path.relative_to(root).as_posix()
        matched = query & (counts.keys() | set(_terms(relative)))
        if not matched:
            continue
        document_frequency.update(matched)
        documents.append((path, text, counts))
    if not documents:
        return ()

    total_documents = len(documents)
    idf = {
        term: math.log((1 + total_documents) / (1 + document_frequency[term]))
        + 1.0
        for term in query
    }
    explicit_paths = {
        match.group("path").lstrip("./")
        for match in _EXPLICIT_PATH.finditer(prompt)
    }
    candidates: list[ReconExcerpt] = []
    for path, text, counts in documents:
        relative = path.relative_to(root).as_posix()
        path_terms = set(_terms(relative))
        coverage = query & counts.keys()
        content_score = sum(idf[term] for term in coverage)
        path_score = sum(24.0 * idf[term] for term in query & path_terms)
        exact_path_score = 100.0 if relative in explicit_paths else 0.0
        lines = text.splitlines()
        start, end, window_score = _best_window(lines, query, idf)
        suspicious_line = _suspicious_guard_line(lines, query)
        anomaly_score = 0.0
        if suspicious_line is not None:
            start = max(0, suspicious_line - 12)
            end = min(len(lines), suspicious_line + 13)
            anomaly_score = 120.0
        source_bias = 1.15 if relative.startswith(("src/", "lib/", "app/")) else 1.0
        score = (
            content_score
            + path_score
            + 4.0 * window_score
            + exact_path_score
            + anomaly_score
        )
        score *= source_bias
        candidates.append(
            ReconExcerpt(
                path=relative,
                start_line=start + 1,
                end_line=end,
                score=score,
                text="\n".join(lines[start:end]),
            )
        )

    ranked = sorted(candidates, key=lambda item: (-item.score, item.path))
    selected: list[ReconExcerpt] = []
    used_chars = 0
    for candidate in ranked:
        remaining = max_chars - used_chars
        if remaining <= 0 or len(selected) >= max_files:
            break
        excerpt_text = candidate.text[:remaining]
        if not excerpt_text.strip():
            continue
        selected.append(
            ReconExcerpt(
                path=candidate.path,
                start_line=candidate.start_line,
                end_line=candidate.end_line,
                score=candidate.score,
                text=excerpt_text,
            )
        )
        used_chars += len(excerpt_text)
    return tuple(selected)


def render_bounded_context(root: Path, prompt: str) -> str:
    excerpts = rank_source_excerpts(root, prompt)
    if not excerpts:
        return (
            "## Precomputed bounded context\n\n"
            "No confident source candidate was found.\n"
        )
    lines = [
        "## Precomputed bounded context",
        "",
        "Generated only from the public task text and visible workspace source.",
        "Candidates are ranked hints; verify the local invariant before editing.",
    ]
    for index, excerpt in enumerate(excerpts, 1):
        language = Path(excerpt.path).suffix.lstrip(".")
        lines.extend(
            [
                "",
                f"### Candidate {index}: {excerpt.path}:{excerpt.start_line}",
                "",
                f"```{language}",
                excerpt.text,
                "```",
            ]
        )
    return "\n".join(lines) + "\n"
