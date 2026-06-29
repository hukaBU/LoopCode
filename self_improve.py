"""Small deterministic reflection helper for agent loop projects.

- PROJECT: `<project>/.ai/LESSONS.md` stores project-specific lessons.
- GLOBAL: `~/.loopcode/GLOBAL_LESSONS.md` stores cross-project lessons.

The project driver can call `python self_improve.py <project_path>` after each
cycle. This module writes lessons and metrics only; it does not alter success
criteria or run an LLM.

Tests can isolate global state with LOOPCODE_GLOBAL_DIR.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LESSONS_FILE = "LESSONS.md"
METRICS_FILE = "reports/metrics.jsonl"
MAX_LESSONS = 200
MAX_REPORTS_SCAN = 20
GLOBAL_PROMOTE_THRESHOLD = 2

_LESSONS_HEADER = (
    "# LESSONS - project memory\n\n"
    "> Append-only, deduplicated, bounded. Read by agents at the start of a cycle.\n"
)
_GLOBAL_HEADER = (
    "# GLOBAL LESSONS - cross-project memory\n\n"
    "> Lessons seen in multiple projects become global patterns.\n"
    "> Append-only and deduplicated. Written by self_improve.py.\n"
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _global_dir() -> Path:
    return Path(
        os.environ.get("LOOPCODE_GLOBAL_DIR")
        or (Path.home() / ".loopcode")
    )


def collect_telemetry(ai_dir: Path) -> dict:
    state: dict = {}
    state_path = ai_dir / "STATE.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}

    reports_dir = ai_dir / "reports"
    reports = (
        sorted(
            reports_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:MAX_REPORTS_SCAN]
        if reports_dir.exists()
        else []
    )
    return {
        "current_objective": state.get("current_objective"),
        "phase": state.get("phase"),
        "cycle_count": state.get("cycle_count"),
        "repair_attempts": state.get("repair_attempts"),
        "last_error_signature": state.get("last_error_signature"),
        "report_count": len(reports),
    }


def distill_lessons(telemetry: dict) -> list[str]:
    """Turn telemetry into deterministic, actionable lessons."""

    lessons: list[str] = []
    objective = telemetry.get("current_objective") or "current objective"
    error = telemetry.get("last_error_signature")
    if error:
        lessons.append(
            f"Recurring failure on `{objective}`: signature `{error}`. Check the root "
            "cause and add a targeted guard before retrying."
        )
    repairs = telemetry.get("repair_attempts")
    if isinstance(repairs, int) and repairs >= 2:
        lessons.append(
            f"`{objective}` required {repairs} repairs. Split the objective or strengthen "
            "acceptance criteria to reduce repeated repair cycles."
        )
    return lessons


def _lesson_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def update_lessons(ai_dir: Path, lessons: list[str]) -> int:
    """Append deduplicated lessons to the project LESSONS.md."""

    if not lessons:
        return 0
    path = ai_dir / LESSONS_FILE
    existing = path.read_text(encoding="utf-8") if path.exists() else _LESSONS_HEADER
    seen = set(re.findall(r"<!--id:([0-9a-f]{12})-->", existing))

    new_lines: list[str] = []
    for lesson in lessons:
        lesson_id = _lesson_hash(lesson)
        if lesson_id in seen:
            continue
        seen.add(lesson_id)
        new_lines.append(f"- ({_now()}) {lesson} <!--id:{lesson_id}-->")

    if not new_lines:
        return 0

    body = existing.rstrip() + "\n" + "\n".join(new_lines) + "\n"
    bullets = re.findall(r"(?m)^- .*$", body)
    if len(bullets) > MAX_LESSONS:
        header = body.split("\n- ", 1)[0]
        body = header + "\n" + "\n".join(bullets[-MAX_LESSONS:]) + "\n"
    path.write_text(body, encoding="utf-8")
    return len(new_lines)


def update_global(lessons: list[str], project_name: str) -> int:
    """Promote lessons seen in at least GLOBAL_PROMOTE_THRESHOLD projects."""

    if not lessons:
        return 0

    global_dir = _global_dir()
    global_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = global_dir / "lesson_ledger.json"
    lessons_path = global_dir / "GLOBAL_LESSONS.md"

    ledger: dict = {}
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ledger = {}

    existing = lessons_path.read_text(encoding="utf-8") if lessons_path.exists() else _GLOBAL_HEADER
    already = set(re.findall(r"<!--id:([0-9a-f]{12})-->", existing))
    promoted: list[str] = []

    for lesson in lessons:
        lesson_id = _lesson_hash(lesson)
        entry = ledger.setdefault(lesson_id, {"text": lesson, "projects": []})
        if project_name not in entry["projects"]:
            entry["projects"].append(project_name)
        if len(entry["projects"]) >= GLOBAL_PROMOTE_THRESHOLD and lesson_id not in already:
            already.add(lesson_id)
            projects = ", ".join(entry["projects"])
            promoted.append(f"- ({_now()}) {entry['text']} <!--id:{lesson_id}--> (seen in: {projects})")

    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    if promoted:
        lessons_path.write_text(existing.rstrip() + "\n" + "\n".join(promoted) + "\n", encoding="utf-8")
    return len(promoted)


def record_metrics(ai_dir: Path, telemetry: dict) -> bool:
    reports_dir = ai_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    keys = ("current_objective", "phase", "cycle_count", "repair_attempts", "last_error_signature")
    snapshot = {key: telemetry.get(key) for key in keys}
    path = ai_dir / METRICS_FILE

    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            if lines and all(json.loads(lines[-1]).get(key) == snapshot[key] for key in keys):
                return False
        except (OSError, ValueError):
            pass

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": _now(), **snapshot}, ensure_ascii=False) + "\n")
    return True


def reflect(project_path: str | Path) -> dict:
    """Reflect one project: project lessons, global promotion, and metrics."""

    ai_dir = Path(project_path) / ".ai"
    if not ai_dir.exists():
        return {"ok": False, "error": f".ai/ not found in {project_path}"}

    telemetry = collect_telemetry(ai_dir)
    lessons = distill_lessons(telemetry)
    added = update_lessons(ai_dir, lessons)
    promoted = update_global(lessons, Path(project_path).resolve().name)
    record_metrics(ai_dir, telemetry)
    return {
        "ok": True,
        "lessons_added": added,
        "global_promoted": promoted,
        "telemetry": telemetry,
    }


def reflect_all(config_path: Path | None = None) -> list[dict]:
    cfg = config_path or (Path(__file__).resolve().parent / "config.json")
    projects: list = []
    if cfg.exists():
        try:
            projects = json.loads(cfg.read_text(encoding="utf-8")).get("projects", [])
        except (OSError, ValueError):
            projects = []
    if not projects:
        try:
            from launcher import DEFAULT_CONFIG

            projects = DEFAULT_CONFIG["projects"]
        except Exception:
            projects = []

    out: list[dict] = []
    for project in projects:
        if isinstance(project, dict) and project.get("path"):
            out.append({"name": project.get("name", project["path"]), **reflect(project["path"])})
    return out


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "--all":
        results = reflect_all()
        local_count = sum(result.get("lessons_added", 0) for result in results if result.get("ok"))
        global_count = sum(result.get("global_promoted", 0) for result in results if result.get("ok"))
        print(f"reflect --all: {len(results)} project(s), +{local_count} project lesson(s), +{global_count} global")
        return 0

    if len(argv) < 2:
        print('usage: python self_improve.py "<project_path>"  |  python self_improve.py --all')
        return 2

    result = reflect(argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
