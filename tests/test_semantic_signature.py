from pathlib import Path

import pytest

from tldr_swinton import semantic
from tldr_swinton.hybrid_extractor import TREE_SITTER_AVAILABLE


@pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter-typescript not available")
def test_semantic_signature_uses_language_specific_format(tmp_path: Path) -> None:
    ts = tmp_path / "mod.ts"
    ts.write_text("export function greet(name: string): string { return name }\n")

    sig = semantic._get_function_signature(ts, "greet", "typescript")
    assert sig is not None
    assert sig.startswith("function ")
