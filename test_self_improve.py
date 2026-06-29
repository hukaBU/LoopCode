"""Tests for self_improve using only the Python standard library."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["LOOPCODE_GLOBAL_DIR"] = tempfile.mkdtemp()

import self_improve as si


class SelfImproveTests(unittest.TestCase):
    def _project(self, state: dict, name: str = "") -> Path:
        root = Path(tempfile.mkdtemp(prefix=(name or "proj") + "_"))
        ai_dir = root / ".ai"
        (ai_dir / "reports").mkdir(parents=True)
        (ai_dir / "STATE.json").write_text(json.dumps(state), encoding="utf-8")
        return root

    def test_lesson_from_error_signature(self) -> None:
        root = self._project(
            {
                "current_objective": "OBJ-120",
                "last_error_signature": "sig-x",
                "repair_attempts": 3,
            }
        )
        result = si.reflect(root)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["lessons_added"], 1)
        self.assertIn("sig-x", (root / ".ai" / "LESSONS.md").read_text(encoding="utf-8"))

    def test_dedup_same_telemetry(self) -> None:
        root = self._project(
            {
                "current_objective": "OBJ-1",
                "last_error_signature": "e",
                "repair_attempts": 2,
            }
        )
        self.assertGreaterEqual(si.reflect(root)["lessons_added"], 1)
        self.assertEqual(si.reflect(root)["lessons_added"], 0)

    def test_metrics_dedup_unchanged(self) -> None:
        root = self._project({"current_objective": "OBJ-9", "cycle_count": 3})
        si.reflect(root)
        si.reflect(root)
        lines = (root / ".ai" / "reports" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)

    def test_global_promotion_two_projects(self) -> None:
        state = {
            "current_objective": "OBJ-X",
            "last_error_signature": "boom",
            "repair_attempts": 2,
        }
        first = si.reflect(self._project(state, "alpha"))
        self.assertEqual(first["global_promoted"], 0)
        second = si.reflect(self._project(state, "beta"))
        self.assertGreaterEqual(second["global_promoted"], 1)
        global_lessons = (
            Path(os.environ["LOOPCODE_GLOBAL_DIR"]) / "GLOBAL_LESSONS.md"
        ).read_text(encoding="utf-8")
        self.assertIn("boom", global_lessons)

    def test_no_ai_dir_fails_cleanly(self) -> None:
        self.assertFalse(si.reflect(Path(tempfile.mkdtemp()))["ok"])


if __name__ == "__main__":
    unittest.main()
