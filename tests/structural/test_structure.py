"""Tests for plugin structure."""

import sys
from pathlib import Path

# Add interverse/ to path so _shared package is importable
_interverse = Path(__file__).resolve().parents[3]
if str(_interverse) not in sys.path:
    sys.path.insert(0, str(_interverse))

from _shared.tests.structural.test_base import StructuralTests


class TestStructure(StructuralTests):
    """Structural tests -- inherits shared base, adds plugin-specific checks."""

    def test_plugin_name(self, plugin_json):
        assert plugin_json["name"] == "tldr-swinton"

    def test_scripts_count(self, project_root):
        """Expected number of scripts."""
        scripts_dir = project_root / "scripts"
        if not scripts_dir.is_dir():
            assert False, "Expected scripts/ directory"
            return
        scripts = list(scripts_dir.glob("*.sh"))
        assert len(scripts) == 6, (
            f"Expected 6 scripts, found {len(scripts)}: {[s.name for s in scripts]}"
        )
