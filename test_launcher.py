"""Tests for launcher configuration and provider switching helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher


class LauncherConfigTests(unittest.TestCase):
    def test_default_config_is_empty(self) -> None:
        self.assertEqual(launcher.DEFAULT_CONFIG, {"projects": []})

    def test_load_provider_config_from_file(self) -> None:
        root = Path(tempfile.mkdtemp())
        providers = root / "providers.json"
        providers.write_text(
            json.dumps(
                {
                    "profile_name": "custom",
                    "providers": {
                        "primary": {"label": "A", "model": "vendor/a"},
                        "secondary": {"label": "B", "model": "vendor/b"},
                        "alternate": {"label": "C", "model": "vendor/c"},
                    },
                    "agents": {"primary": ["lead"], "secondary": ["coder"]},
                    "fallbacks": {"vendor/b": ["vendor/c"]},
                }
            ),
            encoding="utf-8",
        )

        config = launcher.load_provider_config(providers, root / "missing.example.json")

        self.assertEqual(config["profile_name"], "custom")
        self.assertEqual(config["providers"]["primary"]["model"], "vendor/a")
        self.assertEqual(config["agents"]["secondary"], ["coder"])
        self.assertEqual(config["fallbacks"], {"vendor/b": ["vendor/c"]})

    def test_apply_provider_rewrites_opencode_and_agent_frontmatter(self) -> None:
        root = Path(tempfile.mkdtemp())
        opencode = root / ".opencode"
        agents = opencode / "agents"
        agents.mkdir(parents=True)
        (root / "auto-sentinel.ps1").write_text("$profileName = 'agentic'\n", encoding="utf-8")
        (opencode / "opencode.json").write_text(
            json.dumps({"agent": {"lead": {"model": "old"}, "coder": {"model": "old"}}}),
            encoding="utf-8",
        )
        (agents / "lead.md").write_text("---\nmodel: old\n---\n", encoding="utf-8")
        (agents / "coder.md").write_text("---\nmodel: old\n---\n", encoding="utf-8")

        with patch("launcher._provider_available", return_value=True):
            resolved = launcher.apply_provider(root, "mixed")

        data = json.loads((opencode / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(data["agent"]["lead"]["model"], launcher.PRIMARY_MODEL)
        self.assertEqual(data["agent"]["coder"]["model"], launcher.SECONDARY_MODEL)
        self.assertEqual(resolved["lead"], launcher.PRIMARY_MODEL)
        self.assertIn(f"model: {launcher.PRIMARY_MODEL}", (agents / "lead.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
