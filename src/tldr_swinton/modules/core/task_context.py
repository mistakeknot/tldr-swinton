"""Deterministic task-to-source packets for agent harnesses.

The ranker deliberately uses only public task text and visible workspace source.
It is cheap enough to run before an agent starts and does not require a semantic
index, embedding model, or an agent tool call.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


_SOURCE_SUFFIXES = {
    ".bash",
    ".bats",
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
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".zsh",
}
_SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".tldrs",
    ".venv",
    ".worktree",
    ".worktrees",
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
_DEFAULT_PACKET_MAX_CHARS = 1_500
_CODEX_OWNER_HINT_MAX_CHARS = 750


@dataclass(frozen=True)
class TaskContextExcerpt:
    """One ranked, line-addressable source excerpt."""

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


def _test_owner_terms(test_command: str | None) -> set[str]:
    """Derive likely source-owner terms from explicit test file paths."""

    if not test_command:
        return set()
    owner_terms: set[str] = set()
    for match in _EXPLICIT_PATH.finditer(test_command):
        path = Path(match.group("path"))
        stem = path.stem.lower()
        parts = {part.lower() for part in path.parts}
        is_test_path = bool(parts & {"test", "tests", "spec", "specs"})
        is_test_name = stem.startswith(("test_", "spec_")) or stem.endswith(
            ("_test", "_spec")
        )
        if not is_test_path and not is_test_name:
            continue
        owner = re.sub(r"^(?:test|spec)[_-]", "", stem)
        owner = re.sub(r"[_-](?:test|spec)$", "", owner)
        owner_terms.update(_terms(owner))
    return owner_terms


def _is_test_source(relative: str) -> bool:
    path = Path(relative)
    stem = path.stem.lower()
    parts = {part.lower() for part in path.parts}
    return bool(parts & {"test", "tests", "spec", "specs"}) or stem.startswith(
        ("test_", "spec_")
    ) or stem.endswith(("_test", "_spec"))


def recommended_packet_max_chars(
    harness_profile: str,
    test_command: str | None = None,
) -> int:
    """Return the validated packet budget for a harness and owner signal."""

    if harness_profile not in {"generic", "codex", "claude"}:
        raise ValueError(f"unknown harness profile: {harness_profile}")
    if harness_profile == "codex" and _test_owner_terms(test_command):
        return _CODEX_OWNER_HINT_MAX_CHARS
    return _DEFAULT_PACKET_MAX_CHARS


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
    test_command: str | None = None,
    max_files: int = 3,
    max_chars: int = _DEFAULT_PACKET_MAX_CHARS,
) -> tuple[TaskContextExcerpt, ...]:
    """Rank compact source windows likely to own the task's local invariant."""

    root = Path(root)
    test_owner_terms = _test_owner_terms(test_command)
    query = set(_terms(prompt)) | test_owner_terms
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
        term: math.log((1 + total_documents) / (1 + document_frequency[term])) + 1.0
        for term in query
    }
    explicit_paths = {
        match.group("path").lstrip("./") for match in _EXPLICIT_PATH.finditer(prompt)
    }
    candidates: list[TaskContextExcerpt] = []
    for path, text, counts in documents:
        relative = path.relative_to(root).as_posix()
        path_terms = set(_terms(relative))
        coverage = query & counts.keys()
        content_score = sum(idf[term] for term in coverage)
        path_score = sum(24.0 * idf[term] for term in query & path_terms)
        exact_path_score = 100.0 if relative in explicit_paths else 0.0
        test_owner_score = (
            96.0
            if test_owner_terms & set(_terms(path.stem))
            and not _is_test_source(relative)
            else 0.0
        )
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
            + test_owner_score
            + anomaly_score
        )
        score *= source_bias
        candidates.append(
            TaskContextExcerpt(
                path=relative,
                start_line=start + 1,
                end_line=end,
                score=score,
                text="\n".join(lines[start:end]),
            )
        )

    ranked = sorted(candidates, key=lambda item: (-item.score, item.path))
    selected: list[TaskContextExcerpt] = []
    used_chars = 0
    for candidate in ranked:
        remaining = max_chars - used_chars
        if remaining <= 0 or len(selected) >= max_files:
            break
        excerpt_text = candidate.text[:remaining]
        if not excerpt_text.strip():
            continue
        selected.append(
            TaskContextExcerpt(
                path=candidate.path,
                start_line=candidate.start_line,
                end_line=candidate.end_line,
                score=candidate.score,
                text=excerpt_text,
            )
        )
        used_chars += len(excerpt_text)
    return tuple(selected)


def render_bounded_context(
    root: Path,
    prompt: str,
    *,
    test_command: str | None = None,
    max_files: int = 3,
    max_chars: int = _DEFAULT_PACKET_MAX_CHARS,
) -> str:
    """Render ranked excerpts as a compact Markdown context block."""

    excerpts = rank_source_excerpts(
        root,
        prompt,
        test_command=test_command,
        max_files=max_files,
        max_chars=max_chars,
    )
    if not excerpts:
        return "## Precomputed bounded context\n\nNo confident source candidate was found.\n"
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


def render_agent_packet(
    root: Path,
    prompt: str,
    *,
    test_command: str | None = None,
    max_files: int = 3,
    max_chars: int = _DEFAULT_PACKET_MAX_CHARS,
) -> str:
    """Render middleware-ready guidance plus bounded source context."""

    sections = [
        "# Agent context packet",
        "",
        "Use the precomputed candidates below to bound the first source read. Do not "
        "perform repository-wide discovery or invoke additional reconnaissance tools. "
        "Read full source where needed for a safe edit; the packet is not a substitute "
        "for verification.",
    ]
    if test_command:
        sections.extend(
            [
                "",
                "## Validated execution contract",
                "",
                f"Run focused tests with `{test_command}` and append target paths.",
                "Do not probe alternative interpreters or package managers unless this "
                "command cannot start.",
            ]
        )
    sections.extend(
        [
            "",
            render_bounded_context(
                root,
                prompt,
                test_command=test_command,
                max_files=max_files,
                max_chars=max_chars,
            ).rstrip(),
        ]
    )
    return "\n".join(sections) + "\n"


# Backwards-compatible name used by the paired agent evaluator.
ReconExcerpt = TaskContextExcerpt


__all__ = [
    "ReconExcerpt",
    "TaskContextExcerpt",
    "rank_source_excerpts",
    "recommended_packet_max_chars",
    "render_agent_packet",
    "render_bounded_context",
]
