from pathlib import Path


def test_install_script_uses_semantic_ollama_extra() -> None:
    script = Path("scripts/install.sh").read_text()

    assert 'SEMANTIC_EXTRA="semantic-ollama"' in script
    assert "command -v ollama" in script
    assert 'uv sync --extra "$SEMANTIC_EXTRA"' in script
    assert 'uv pip install -e ".[${SEMANTIC_EXTRA}]"' in script
