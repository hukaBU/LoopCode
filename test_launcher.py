"""Tests for launcher configuration, model switching, and auth helpers."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher


class LauncherConfigTests(unittest.TestCase):
    def test_default_config_is_empty(self) -> None:
        self.assertEqual(launcher.DEFAULT_CONFIG, {"projects": []})

    def test_load_provider_config_from_new_file_shape(self) -> None:
        root = Path(tempfile.mkdtemp())
        providers = root / "providers.json"
        providers.write_text(
            json.dumps(
                {
                    "profile_name": "custom",
                    "model": "vendor/a",
                    "models": ["vendor/a", "vendor/b"],
                    "agents": {"all": ["lead", "coder"]},
                }
            ),
            encoding="utf-8",
        )

        config = launcher.load_provider_config(providers, root / "missing.example.json")

        self.assertEqual(config["profile_name"], "custom")
        self.assertEqual(config["model"], "vendor/a")
        self.assertEqual(config["models"], ["vendor/a", "vendor/b"])
        self.assertEqual(config["agents"]["all"], ["lead", "coder"])

    def test_load_provider_config_supports_legacy_provider_shape(self) -> None:
        config = launcher.load_provider_config_from_data(
            {
                "profile_name": "legacy",
                "providers": {
                    "primary": {"model": "vendor/a", "models": ["vendor/a-fast"]},
                    "secondary": {"model": "vendor/b"},
                },
                "agents": {"primary": ["lead"], "secondary": ["coder"]},
            }
        )

        self.assertEqual(config["profile_name"], "legacy")
        self.assertEqual(config["model"], "vendor/a")
        self.assertIn("vendor/a-fast", config["models"])
        self.assertEqual(config["agents"]["all"], ["lead", "coder"])

    def test_apply_model_rewrites_opencode_and_agent_frontmatter(self) -> None:
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

        with patch.object(launcher, "ALL_AGENTS", ("lead", "coder")):
            resolved = launcher.apply_model(root, "vendor/new")

        data = json.loads((opencode / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(data["agent"]["lead"]["model"], "vendor/new")
        self.assertEqual(data["agent"]["coder"]["model"], "vendor/new")
        self.assertEqual(resolved["lead"], "vendor/new")
        self.assertIn("model: vendor/new", (agents / "lead.md").read_text(encoding="utf-8"))

    def test_current_project_model_detects_mixed(self) -> None:
        root = Path(tempfile.mkdtemp())
        opencode = root / ".opencode"
        agents = opencode / "agents"
        agents.mkdir(parents=True)
        (opencode / "opencode.json").write_text(
            json.dumps({"agent": {"lead": {"model": "a"}, "coder": {"model": "b"}}}),
            encoding="utf-8",
        )

        with patch.object(launcher, "ALL_AGENTS", ("lead", "coder")):
            self.assertEqual(launcher.current_project_model(root), "mixed")

    def test_build_obj_prompt_mentions_project(self) -> None:
        prompt = launcher.build_obj_prompt({"name": "Demo", "path": "C:\\Demo"})

        self.assertIn("Project name: Demo", prompt)
        self.assertIn("OBJ-0", prompt)
        self.assertIn("Acceptance criteria", prompt)

    def test_setup_project_auth_creates_missing_profile_then_opens_login(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["opencode-multi", "create", "demo"],
            returncode=0,
            stdout="created",
            stderr="",
        )

        with (
            patch("launcher.opencode_profile_exists", return_value=False),
            patch("launcher.create_opencode_profile", return_value=completed) as create_profile,
            patch("launcher.open_opencode_login") as open_login,
        ):
            ok, message = launcher.setup_project_auth("C:\\Demo", "demo")

        self.assertTrue(ok)
        self.assertEqual(message, "demo")
        create_profile.assert_called_once_with("demo", init=True)
        open_login.assert_called_once_with("C:\\Demo", "demo")


if __name__ == "__main__":
    unittest.main()
