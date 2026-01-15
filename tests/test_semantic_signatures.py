from pathlib import Path

from tldr_swinton.semantic import _get_signature_via_extractor


def test_semantic_signature_uses_language(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.ts"
    file_path.write_text(
        "export async function foo(x: number): Promise<void> { return; }\n"
    )

    signature = _get_signature_via_extractor(file_path, "foo")
    assert signature is not None
    assert signature.strip().startswith("async function foo(")
