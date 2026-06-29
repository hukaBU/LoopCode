"""LoopCode - desktop helper for opencode-multi projects.

The app keeps a local list of projects, launches each project's PowerShell
driver in a new console, and rewrites configured agent model ids when switching
provider modes.

Driver contract:
  - each project has an auto-sentinel.ps1 driver at its root,
  - each project has .opencode/opencode.json and .opencode/agents/*.md,
  - opencode-multi is installed and authenticated for the selected providers.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "config.json"
PROVIDERS_FILE = APP_DIR / "providers.json"
PROVIDERS_EXAMPLE_FILE = APP_DIR / "providers.example.json"

DEFAULT_CONFIG = {"projects": []}

DEFAULT_PROVIDER_CONFIG = {
    "profile_name": "agentic",
    "providers": {
        "primary": {"label": "Primary model", "model": "provider/primary-model"},
        "secondary": {"label": "Secondary model", "model": "provider/secondary-model"},
        "alternate": {"label": "Alternate model", "model": "provider/alternate-model"},
    },
    "agents": {
        "primary": ["lead", "security", "reviewer", "debugger"],
        "secondary": ["coder", "researcher", "tester", "docs"],
    },
    "fallbacks": {},
}

# --- Theme -------------------------------------------------------------------
BG = "#0f1117"
PANEL = "#171a21"
FG = "#e6e8eb"
MUTED = "#8b93a1"
CYAN = "#22d3ee"
GREEN = "#16a34a"
BLUE = "#2563eb"
PURPLE = "#7c3aed"
RED = "#b91c1c"
ORANGE = "#ea580c"


def _deepcopy_json(data: dict) -> dict:
    return json.loads(json.dumps(data))


def _read_json_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _clean_string(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _clean_string_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return cleaned or list(fallback)


def load_provider_config(
    config_path: Path | None = None,
    example_path: Path | None = None,
) -> dict:
    """Load provider settings from providers.json, then providers.example.json.

    providers.json is intentionally git-ignored. providers.example.json gives a
    public template and a runnable default for people using the same providers.
    """

    cfg = copy.deepcopy(DEFAULT_PROVIDER_CONFIG)
    paths = (
        config_path or PROVIDERS_FILE,
        example_path or PROVIDERS_EXAMPLE_FILE,
    )
    raw: dict | None = None
    for path in paths:
        if path.exists():
            raw = _read_json_file(path)
            if raw is not None:
                break
    if raw is None:
        return cfg

    cfg["profile_name"] = _clean_string(raw.get("profile_name"), cfg["profile_name"])

    providers = raw.get("providers")
    if isinstance(providers, dict):
        for key, fallback in cfg["providers"].items():
            provider = providers.get(key)
            if not isinstance(provider, dict):
                continue
            cfg["providers"][key] = {
                "label": _clean_string(provider.get("label"), fallback["label"]),
                "model": _clean_string(provider.get("model"), fallback["model"]),
            }

    agents = raw.get("agents")
    if isinstance(agents, dict):
        cfg["agents"]["primary"] = _clean_string_list(
            agents.get("primary"),
            cfg["agents"]["primary"],
        )
        cfg["agents"]["secondary"] = _clean_string_list(
            agents.get("secondary"),
            cfg["agents"]["secondary"],
        )

    fallbacks = raw.get("fallbacks")
    if isinstance(fallbacks, dict):
        cleaned: dict[str, list[str]] = {}
        for model, candidates in fallbacks.items():
            if not isinstance(model, str) or not model.strip():
                continue
            if isinstance(candidates, str):
                values = [candidates]
            else:
                values = candidates
            cleaned[model.strip()] = _clean_string_list(values, [])
        cfg["fallbacks"] = cleaned

    return cfg


PROVIDER_CONFIG = load_provider_config()
PROFILE_NAME = PROVIDER_CONFIG["profile_name"]
PROVIDERS = PROVIDER_CONFIG["providers"]
PRIMARY_MODEL = PROVIDERS["primary"]["model"]
SECONDARY_MODEL = PROVIDERS["secondary"]["model"]
ALTERNATE_MODEL = PROVIDERS["alternate"]["model"]
PRIMARY_AGENTS = tuple(PROVIDER_CONFIG["agents"]["primary"])
SECONDARY_AGENTS = tuple(PROVIDER_CONFIG["agents"]["secondary"])
ALL_AGENTS = tuple(dict.fromkeys((*PRIMARY_AGENTS, *SECONDARY_AGENTS)))
MODEL_FALLBACKS = {
    model: tuple(candidates)
    for model, candidates in PROVIDER_CONFIG.get("fallbacks", {}).items()
}
PROVIDER_CACHE: dict[str, bool] = {}


def provider_label(key: str) -> str:
    provider = PROVIDERS.get(key, {})
    label = provider.get("label") if isinstance(provider, dict) else None
    return str(label or key)


def mode_label(mode: str) -> str:
    primary = provider_label("primary")
    secondary = provider_label("secondary")
    alternate = provider_label("alternate")
    labels = {
        "mixed": f"{primary} + {secondary}",
        "primary_only": f"{primary} only",
        "secondary": f"{secondary} only",
        "alternate": f"{alternate} only",
        "primary_alternate": f"{primary} + {alternate}",
        "unknown": "unknown",
    }
    return labels.get(mode, labels["unknown"])


# =========================================================================
# Logic without UI - easy to test and reuse
# =========================================================================


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("projects"), list):
                return data
        except (OSError, ValueError):
            pass
    return _deepcopy_json(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def _agent_model(opencode_dir: Path, agent: str) -> str:
    """Return one agent's model id from opencode.json or agent frontmatter."""

    try:
        data = json.loads((opencode_dir / "opencode.json").read_text(encoding="utf-8"))
        model = str(data.get("agent", {}).get(agent, {}).get("model", ""))
        if model:
            return model
    except (OSError, ValueError, AttributeError):
        pass
    try:
        text = (opencode_dir / "agents" / f"{agent}.md").read_text(encoding="utf-8")
        match = re.search(r"(?m)^model:\s*(.+)$", text)
        if match:
            return match.group(1).strip()
    except OSError:
        pass
    return ""


def _provider_key(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else ""


def _provider_available(model: str, profile: str = PROFILE_NAME) -> bool:
    provider = _provider_key(model)
    if not provider:
        return False
    cache_key = f"{profile}:{provider}"
    cached = PROVIDER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        result = subprocess.run(
            ["opencode-multi", "run", profile, "models", provider],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        PROVIDER_CACHE[cache_key] = False
        return False
    available = result.returncode == 0 and model in result.stdout.split()
    PROVIDER_CACHE[cache_key] = available
    return available


def _resolve_model(model: str, profile: str = PROFILE_NAME) -> tuple[str, bool]:
    for candidate in (model, *MODEL_FALLBACKS.get(model, ())):
        if _provider_available(candidate, profile):
            return candidate, candidate != model
    return model, False


def project_profile(project_path: str) -> str:
    """Return the opencode-multi profile used by the project's driver.

    The driver may define `$profileName = '...'` in auto-*.ps1. If the driver is
    missing or does not set a profile, the configured default profile is used.
    """

    try:
        ps1_files = sorted(Path(project_path).glob("auto-*.ps1"))
    except OSError:
        return PROFILE_NAME
    for ps1 in ps1_files:
        try:
            text = ps1.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        match = re.search(r"(?m)^\s*\$profileName\s*=\s*['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1)
    return PROFILE_NAME


def _model_matches(model: str, expected: str) -> bool:
    return bool(model) and model == expected


def detect_provider(project_path: str) -> str:
    """Return the effective provider mode from configured agent models."""

    opencode_dir = Path(project_path) / ".opencode"
    primary_agent = PRIMARY_AGENTS[0] if PRIMARY_AGENTS else "lead"
    secondary_agent = SECONDARY_AGENTS[0] if SECONDARY_AGENTS else "coder"
    primary_model = _agent_model(opencode_dir, primary_agent)

    if _model_matches(primary_model, PRIMARY_MODEL):
        secondary_model = _agent_model(opencode_dir, secondary_agent)
        if _model_matches(secondary_model, PRIMARY_MODEL):
            return "primary_only"
        if _model_matches(secondary_model, SECONDARY_MODEL):
            return "mixed"
        if _model_matches(secondary_model, ALTERNATE_MODEL):
            return "primary_alternate"
        return "mixed"
    if _model_matches(primary_model, SECONDARY_MODEL):
        return "secondary"
    if _model_matches(primary_model, ALTERNATE_MODEL):
        return "alternate"
    return "unknown"


def requested_models_for_mode(mode: str) -> dict[str, str]:
    if mode == "secondary":
        return {agent: SECONDARY_MODEL for agent in ALL_AGENTS}
    if mode == "alternate":
        return {agent: ALTERNATE_MODEL for agent in ALL_AGENTS}
    if mode == "primary_only":
        return {agent: PRIMARY_MODEL for agent in ALL_AGENTS}
    return {
        agent: (PRIMARY_MODEL if agent in PRIMARY_AGENTS else SECONDARY_MODEL)
        for agent in ALL_AGENTS
    }


def apply_provider(project_path: str, mode: str) -> dict[str, str]:
    """Rewrite configured agent models and apply authenticated fallbacks."""

    opencode_dir = Path(project_path) / ".opencode"
    config_file = opencode_dir / "opencode.json"
    if not config_file.exists():
        raise FileNotFoundError(f".opencode/opencode.json not found in {project_path}")

    requested_models = requested_models_for_mode(mode)
    profile = project_profile(project_path)
    resolved_models = {
        agent: _resolve_model(model, profile)[0]
        for agent, model in requested_models.items()
    }

    data = json.loads(config_file.read_text(encoding="utf-8"))
    for name, agent_cfg in data.get("agent", {}).items():
        if name in resolved_models and isinstance(agent_cfg, dict) and "model" in agent_cfg:
            agent_cfg["model"] = resolved_models[name]
    config_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    for name, model in resolved_models.items():
        md = opencode_dir / "agents" / f"{name}.md"
        if md.exists():
            text = md.read_text(encoding="utf-8")
            new_text = re.sub(r"(?m)^model:.*$", f"model: {model}", text, count=1)
            if new_text != text:
                md.write_text(new_text, encoding="utf-8")
    return resolved_models


def launch_loop(project_path: str, *, resume: bool = False) -> None:
    """Launch auto-sentinel.ps1 in a new Windows PowerShell console."""

    ps1 = Path(project_path) / "auto-sentinel.ps1"
    if not ps1.exists():
        raise FileNotFoundError(f"auto-sentinel.ps1 not found in {project_path}")
    if not hasattr(subprocess, "CREATE_NEW_CONSOLE"):
        raise OSError("Launching loops is currently Windows-only because it uses PowerShell consoles.")

    args = ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(ps1)]
    if resume:
        args.append("-Resume")
    subprocess.Popen(
        args,
        cwd=str(project_path),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


# =========================================================================
# UI
# =========================================================================


class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config = load_config()

        root.title("LoopCode")
        root.geometry("860x600")
        root.minsize(680, 520)
        root.configure(bg=BG)

        self._build_header()
        self._build_provider_panel()
        self._build_projects_panel()
        self._build_actions()
        self._build_log()

        self.refresh_projects()
        self.log("Ready. Select a project, choose a provider mode, then launch.")

    # -- UI construction ------------------------------------------------------

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(
            header,
            text="LoopCode",
            bg=BG,
            fg=CYAN,
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")

    def _build_provider_panel(self) -> None:
        panel = tk.Frame(self.root, bg=PANEL)
        panel.pack(fill="x", padx=16, pady=6)
        tk.Label(
            panel,
            text="Provider mode for selected project:",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 2))

        self.provider_value = tk.Label(
            panel,
            text="-",
            bg=PANEL,
            fg=FG,
            font=("Segoe UI", 11, "bold"),
        )
        self.provider_value.grid(row=1, column=0, columnspan=4, sticky="w", padx=12)

        buttons = (
            ("secondary", f"{provider_label('secondary')} only", GREEN),
            ("mixed", f"{provider_label('primary')} + {provider_label('secondary')}", BLUE),
            ("alternate", f"{provider_label('alternate')} only", PURPLE),
            ("primary_only", f"{provider_label('primary')} only", ORANGE),
        )
        for column, (mode, label, color) in enumerate(buttons):
            tk.Button(
                panel,
                text=label,
                bg=color,
                fg="white",
                activebackground=color,
                activeforeground="white",
                relief="flat",
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
                padx=10,
                pady=6,
                command=lambda value=mode: self.switch_provider(value),
            ).grid(row=2, column=column, sticky="w", padx=(12 if column == 0 else 4), pady=10)

    def _build_projects_panel(self) -> None:
        panel = tk.Frame(self.root, bg=BG)
        panel.pack(fill="both", expand=True, padx=16, pady=6)
        tk.Label(
            panel,
            text="Saved projects:",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        list_frame = tk.Frame(panel, bg=BG)
        list_frame.pack(fill="both", expand=True, pady=(4, 0))
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            list_frame,
            bg=PANEL,
            fg=FG,
            selectbackground=CYAN,
            selectforeground="#06121a",
            font=("Consolas", 10),
            relief="flat",
            highlightthickness=0,
            activestyle="none",
            yscrollcommand=scrollbar.set,
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self.on_select())
        self.listbox.bind("<Double-Button-1>", lambda _e: self.do_launch())

    def _build_actions(self) -> None:
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=16, pady=(2, 6))

        tk.Button(
            bar,
            text="Launch loop",
            bg=CYAN,
            fg="#06121a",
            activebackground="#0891b2",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=16,
            pady=8,
            command=self.do_launch,
        ).pack(side="left")

        self.resume_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            bar,
            text="Resume (-Resume)",
            variable=self.resume_var,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 9),
            relief="flat",
            highlightthickness=0,
        ).pack(side="left", padx=10)

        tk.Button(
            bar,
            text="Remove",
            bg=PANEL,
            fg=FG,
            activebackground=RED,
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=12,
            pady=8,
            command=self.remove_project,
        ).pack(side="right")
        tk.Button(
            bar,
            text="Add project",
            bg=PANEL,
            fg=FG,
            activebackground="#2a2f3a",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=12,
            pady=8,
            command=self.add_project,
        ).pack(side="right", padx=8)

    def _build_log(self) -> None:
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="x", padx=16, pady=(0, 14))
        self.log_text = tk.Text(
            frame,
            height=6,
            bg="#0b0d12",
            fg=MUTED,
            font=("Consolas", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground="#222733",
            wrap="word",
        )
        self.log_text.pack(fill="x")
        self.log_text.configure(state="disabled")

    # -- UI logic -------------------------------------------------------------

    def projects(self) -> list[dict]:
        return self.config.get("projects", [])

    def selected_index(self) -> int | None:
        selection = self.listbox.curselection()
        return int(selection[0]) if selection else None

    def selected_project(self) -> dict | None:
        index = self.selected_index()
        if index is None or index >= len(self.projects()):
            return None
        return self.projects()[index]

    def refresh_projects(self) -> None:
        self.listbox.delete(0, tk.END)
        for project in self.projects():
            self.listbox.insert(tk.END, f"  {project['name']:<22}  {project['path']}")
        if self.projects():
            self.listbox.selection_set(0)
            self.on_select()
        else:
            self.provider_value.config(text="-")

    def on_select(self) -> None:
        project = self.selected_project()
        if project is None:
            self.provider_value.config(text="-")
            return
        provider = detect_provider(project["path"])
        self.provider_value.config(text=mode_label(provider))

    def switch_provider(self, mode: str) -> None:
        project = self.selected_project()
        if project is None:
            messagebox.showinfo("LoopCode", "Select a project first.")
            return
        try:
            resolved_models = apply_provider(project["path"], mode)
        except (OSError, ValueError) as exc:
            messagebox.showerror("LoopCode", f"Provider switch failed: {exc}")
            self.log(f"Provider switch failed: {exc}")
            return
        self.on_select()
        self.log(f"{project['name']} -> {mode_label(mode)}")

        fallback_notes = []
        for agent, requested_model in requested_models_for_mode(mode).items():
            applied_model = resolved_models.get(agent, requested_model)
            if applied_model != requested_model:
                fallback_notes.append(f"{agent}: {requested_model} -> {applied_model}")
        if fallback_notes:
            profile = project_profile(project["path"])
            self.log(
                f"Requested provider is not authenticated in profile '{profile}'. "
                "Fallback: " + " | ".join(fallback_notes)
            )
            self.log(f"Authenticate with: opencode-multi run {profile} models")

    def do_launch(self) -> None:
        project = self.selected_project()
        if project is None:
            messagebox.showinfo("LoopCode", "Select a project first.")
            return
        try:
            launch_loop(project["path"], resume=self.resume_var.get())
        except (OSError, ValueError) as exc:
            messagebox.showerror("LoopCode", f"Launch failed: {exc}")
            self.log(f"Launch failed: {exc}")
            return
        provider = mode_label(detect_provider(project["path"]))
        mode = " (resume)" if self.resume_var.get() else ""
        self.log(f"Loop launched: {project['name']}{mode} - {provider}")

    def add_project(self) -> None:
        path = filedialog.askdirectory(title="Choose project folder")
        if not path:
            return
        path = str(Path(path))
        if not (Path(path) / "auto-sentinel.ps1").exists():
            if not messagebox.askyesno(
                "LoopCode",
                "auto-sentinel.ps1 was not found in this folder.\nAdd it anyway?",
            ):
                return
        name = simpledialog.askstring(
            "LoopCode",
            "Project name:",
            initialvalue=Path(path).name,
        )
        if not name:
            name = Path(path).name
        self.projects().append({"name": name, "path": path})
        save_config(self.config)
        self.refresh_projects()
        self.log(f"Project added: {name}")

    def remove_project(self) -> None:
        index = self.selected_index()
        if index is None:
            return
        project = self.projects().pop(index)
        save_config(self.config)
        self.refresh_projects()
        self.log(f"Project removed: {project['name']}")

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")


def main() -> None:
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
