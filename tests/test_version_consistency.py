from __future__ import annotations

import json
import tomllib
from pathlib import Path


def _json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def test_kimi_manifest_tracks_current_package_and_claude_metadata() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    claude = _json(".claude-plugin/plugin.json")
    kimi = _json("kimi.plugin.json")

    assert kimi["version"] == claude["version"] == pyproject["project"]["version"]
    assert kimi["description"] == claude["description"]
    assert kimi["author"] == claude["author"]["name"]


def test_post_bump_keeps_kimi_release_metadata_in_sync() -> None:
    post_bump = Path("scripts/post-bump.sh").read_text()

    assert "kimi.plugin.json" in post_bump
    assert "TARGET_VERSION" in post_bump


def test_kimi_manifest_exposes_current_skills_commands_and_mcp() -> None:
    kimi = _json("kimi.plugin.json")

    assert kimi["skills"] == "./.claude-plugin/skills/"
    assert kimi["commands"] == "./.claude-plugin/commands/"
    assert kimi["mcpServers"]["tldr-code"]["command"] == "./bin/launch-mcp.sh"
    assert kimi["mcpServers"]["tldr-code"]["args"] == ["--project", "."]
    assert "hooks" not in kimi


def test_kimi_manifest_uses_only_supported_current_fields() -> None:
    kimi = _json("kimi.plugin.json")
    supported = {
        "name",
        "version",
        "description",
        "keywords",
        "author",
        "homepage",
        "license",
        "interface",
        "skills",
        "sessionStart",
        "skillInstructions",
        "mcpServers",
        "hooks",
        "commands",
    }

    assert set(kimi) <= supported
    assert len(kimi["interface"]["shortDescription"]) <= 120
