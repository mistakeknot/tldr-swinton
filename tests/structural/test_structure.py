"""Tests for plugin structure."""

import json
import os
from pathlib import Path


def test_plugin_json_valid(project_root):
    """plugin.json is valid JSON with required fields."""
    path = project_root / ".claude-plugin" / "plugin.json"
    assert path.exists(), "Missing .claude-plugin/plugin.json"
    data = json.loads(path.read_text())
    for field in ("name", "version", "description", "author"):
        assert field in data, f"plugin.json missing required field: {field}"
    assert data["name"] == "tldr-swinton"


def test_plugin_json_skills_match_filesystem(project_root, plugin_json):
    """Every skill listed in plugin.json exists on disk."""
    for skill_path in plugin_json.get("skills", []):
        resolved = project_root / skill_path
        assert resolved.is_dir(), f"Skill dir not found: {skill_path}"
        assert (resolved / "SKILL.md").exists(), f"Missing SKILL.md in {skill_path}"


def test_plugin_json_commands_match_filesystem(project_root, plugin_json):
    """Every command listed in plugin.json exists on disk."""
    for cmd_path in plugin_json.get("commands", []):
        resolved = project_root / cmd_path
        assert resolved.exists(), f"Command not found: {cmd_path}"


def test_required_root_files(project_root):
    """All required root-level files exist."""
    required = ["CLAUDE.md", "PHILOSOPHY.md", "LICENSE", ".gitignore"]
    for name in required:
        assert (project_root / name).exists(), f"Missing required file: {name}"


def test_scripts_executable(project_root):
    """All shell scripts are executable."""
    scripts_dir = project_root / "scripts"
    if not scripts_dir.is_dir():
        return
    for script in scripts_dir.glob("*.sh"):
        assert os.access(script, os.X_OK), f"Script not executable: {script.name}"


def test_scripts_count(project_root):
    """Expected number of scripts."""
    scripts_dir = project_root / "scripts"
    if not scripts_dir.is_dir():
        assert 6 == 0, "Expected scripts/ directory"
        return
    scripts = list(scripts_dir.glob("*.sh"))
    assert len(scripts) == 6, (
        f"Expected 6 scripts, found {len(scripts)}: {[s.name for s in scripts]}"
    )
