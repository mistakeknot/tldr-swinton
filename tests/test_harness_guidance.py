import json
from pathlib import Path


def test_claude_reconnaissance_uses_an_explore_fork_for_noisy_work() -> None:
    skill = Path(".claude-plugin/skills/tldrs-session-start/SKILL.md").read_text()

    assert "context: fork" in skill
    assert "agent: Explore" in skill
    assert "unfamiliar" in skill.lower()
    assert "starting any coding task" not in skill.lower()


def test_codex_guidance_is_adaptive_instead_of_a_pre_read_gate() -> None:
    skill = Path(".codex/skills/tldrs-agent-workflow/SKILL.md").read_text()

    assert "Use tldrs when" in skill
    assert "Run tldrs BEFORE using Read" not in skill
    assert "already narrowed" in skill


def test_plugin_does_not_duplicate_content_after_raw_reads() -> None:
    hooks = json.loads(Path(".claude-plugin/hooks/hooks.json").read_text())["hooks"]

    assert set(hooks) == {"Setup"}
    assert not Path(".claude-plugin/hooks/post-read-extract.sh").exists()


def test_setup_hook_checks_executable_health_without_injecting_structure() -> None:
    hook = Path(".claude-plugin/hooks/setup.sh").read_text()

    assert "tldrs --version" in hook
    assert "tldrs structure" not in hook
    assert "will run diff-context" not in hook
