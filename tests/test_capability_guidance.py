from pathlib import Path


def test_quickstart_and_readme_describe_the_adaptive_plugin_surface() -> None:
    quickstart = Path("docs/QUICKSTART.md").read_text()
    readme = Path("README.md").read_text()

    assert "Run tldrs BEFORE using Read" not in quickstart
    assert "Use tldrs when" in quickstart
    assert "6 autonomous skills" not in readme
    assert "forked Explore" in readme


def test_capability_baseline_is_dated_and_uses_primary_sources() -> None:
    baseline = Path("docs/harness-capabilities.md").read_text()

    assert "Last verified: 2026-07-21" in baseline
    assert "https://code.claude.com/docs/en/sub-agents" in baseline
    assert "https://code.claude.com/docs/en/skills" in baseline
    assert "https://developers.openai.com/codex/codex-manual.md" in baseline
    assert "https://developers.openai.com/api/docs/guides/latest-model" in baseline
