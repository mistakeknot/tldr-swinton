from pathlib import Path
import re


def test_no_tldr_imports() -> None:
    repo = Path(__file__).resolve().parents[1]
    matches = []
    for path in repo.rglob("*.py"):
        if "dist" in path.parts or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\bfrom tldr\b|\bimport tldr\b", text):
            matches.append(str(path))
    assert matches == []
