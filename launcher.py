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
import os
import re
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "config.json"
PROVIDERS_FILE = APP_DIR / "providers.json"
PROVIDERS_EXAMPLE_FILE = APP_DIR / "providers.example.json"
SECRETS_FILE = APP_DIR / "secrets.json"

DEFAULT_CONFIG = {"projects": []}

DEFAULT_PROVIDER_CONFIG = {
    "profile_name": "agentic",
    "providers": {
        "primary": {
            "label": "Primary model",
            "model": "provider/primary-model",
            "models": ["provider/primary-model"],
            "api_key_env": "PRIMARY_API_KEY",
        },
        "secondary": {
            "label": "Secondary model",
            "model": "provider/secondary-model",
            "models": ["provider/secondary-model"],
            "api_key_env": "SECONDARY_API_KEY",
        },
        "alternate": {
            "label": "Alternate model",
            "model": "provider/alternate-model",
            "models": ["provider/alternate-model"],
            "api_key_env": "ALTERNATE_API_KEY",
        },
    },
    "agents": {
        "primary": ["lead", "security", "reviewer", "debugger"],
        "secondary": ["coder", "researcher", "tester", "docs"],
    },
    "fallbacks": {},
}
DEFAULT_SECRET_CONFIG = {"api_keys": {}}
PROVIDER_KEYS = ("primary", "secondary", "alternate")

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


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _clean_provider(value: object, fallback: dict) -> dict:
    provider = value if isinstance(value, dict) else {}
    model = _clean_string(provider.get("model"), fallback["model"])
    models = _clean_string_list(provider.get("models"), fallback.get("models", [model]))
    models = _dedupe_strings([model, *models])
    return {
        "label": _clean_string(provider.get("label"), fallback["label"]),
        "model": model,
        "models": models,
        "api_key_env": _clean_string(provider.get("api_key_env"), fallback["api_key_env"]),
    }


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
    return load_provider_config_from_data(raw)


def save_provider_config(config: dict, path: Path | None = None) -> None:
    target = path or PROVIDERS_FILE
    cleaned = load_provider_config_from_data(config)
    target.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")


def load_provider_config_from_data(data: dict) -> dict:
    cfg = copy.deepcopy(DEFAULT_PROVIDER_CONFIG)
    raw = data if isinstance(data, dict) else {}

    cfg["profile_name"] = _clean_string(raw.get("profile_name"), cfg["profile_name"])

    providers = raw.get("providers")
    if isinstance(providers, dict):
        for key in PROVIDER_KEYS:
            cfg["providers"][key] = _clean_provider(
                providers.get(key),
                cfg["providers"][key],
            )

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
            values = [candidates] if isinstance(candidates, str) else candidates
            cleaned[model.strip()] = _clean_string_list(values, [])
        cfg["fallbacks"] = cleaned

    return cfg


def load_secret_config(path: Path | None = None) -> dict:
    raw = _read_json_file(path or SECRETS_FILE) or DEFAULT_SECRET_CONFIG
    api_keys = raw.get("api_keys") if isinstance(raw, dict) else {}
    cleaned: dict[str, str] = {}
    if isinstance(api_keys, dict):
        for key, value in api_keys.items():
            if isinstance(key, str) and isinstance(value, str) and key.strip() and value:
                cleaned[key.strip()] = value
    return {"api_keys": cleaned}


def save_secret_config(config: dict, path: Path | None = None) -> None:
    target = path or SECRETS_FILE
    cleaned = load_secret_config_from_data(config)
    target.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")


def load_secret_config_from_data(data: dict) -> dict:
    api_keys = data.get("api_keys") if isinstance(data, dict) else {}
    cleaned: dict[str, str] = {}
    if isinstance(api_keys, dict):
        for key, value in api_keys.items():
            if isinstance(key, str) and isinstance(value, str) and key.strip() and value:
                cleaned[key.strip()] = value
    return {"api_keys": cleaned}


def runtime_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    for key, value in load_secret_config()["api_keys"].items():
        env[key] = value
    return env


def configure_runtime(config: dict | None = None) -> None:
    global PROVIDER_CONFIG
    global PROFILE_NAME, PROVIDERS, PRIMARY_MODEL, SECONDARY_MODEL, ALTERNATE_MODEL
    global PRIMARY_AGENTS, SECONDARY_AGENTS, ALL_AGENTS, MODEL_FALLBACKS

    PROVIDER_CONFIG = load_provider_config_from_data(config or load_provider_config())
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


def reload_runtime_config() -> None:
    PROVIDER_CACHE.clear()
    configure_runtime(load_provider_config())


PROVIDER_CONFIG: dict = {}
PROFILE_NAME = ""
PROVIDERS: dict = {}
PRIMARY_MODEL = ""
SECONDARY_MODEL = ""
ALTERNATE_MODEL = ""
PRIMARY_AGENTS: tuple[str, ...] = ()
SECONDARY_AGENTS: tuple[str, ...] = ()
ALL_AGENTS: tuple[str, ...] = ()
MODEL_FALLBACKS: dict[str, tuple[str, ...]] = {}
PROVIDER_CACHE: dict[str, bool] = {}
configure_runtime()


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


def _slugify_profile_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or PROFILE_NAME


def _windows_console_flags() -> int:
    if not hasattr(subprocess, "CREATE_NEW_CONSOLE"):
        raise OSError("Interactive opencode commands are currently Windows-only.")
    return subprocess.CREATE_NEW_CONSOLE


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
            env=runtime_env(),
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


def driver_profile(project_path: str) -> str | None:
    """Return `$profileName` from the project driver when it is declared."""

    try:
        ps1_files = sorted(Path(project_path).glob("auto-*.ps1"))
    except OSError:
        return None
    for ps1 in ps1_files:
        try:
            text = ps1.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        match = re.search(r"(?m)^\s*\$profileName\s*=\s*['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1)
    return None


def configured_project_profile(project_path: str) -> str | None:
    config = load_config()
    try:
        target = Path(project_path).resolve()
    except OSError:
        target = Path(project_path)
    for project in config.get("projects", []):
        if not isinstance(project, dict):
            continue
        path = project.get("path")
        profile = project.get("profile")
        if not isinstance(path, str) or not isinstance(profile, str) or not profile.strip():
            continue
        try:
            candidate = Path(path).resolve()
        except OSError:
            candidate = Path(path)
        if candidate == target:
            return profile.strip()
    return None


def project_profile(project_path: str) -> str:
    """Return the opencode-multi profile used by the project.

    The driver `$profileName` is authoritative. If absent, the optional
    `profile` value from config.json is used, then the global default.
    """

    return driver_profile(project_path) or configured_project_profile(project_path) or PROFILE_NAME


def opencode_profile_exists(profile: str) -> bool:
    result = subprocess.run(
        ["opencode-multi", "show", profile],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=runtime_env(),
    )
    return result.returncode == 0


def create_opencode_profile(profile: str, *, init: bool = True) -> subprocess.CompletedProcess[str]:
    args = ["opencode-multi", "create", profile]
    if init:
        args.append("--init")
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=runtime_env(),
    )


def opencode_providers_list(profile: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["opencode-multi", "run", profile, "providers", "list"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=runtime_env(),
    )


def open_opencode_auth(project_path: str, profile: str) -> None:
    subprocess.Popen(
        ["opencode-multi", "run", profile, "providers", "login"],
        cwd=str(project_path),
        creationflags=_windows_console_flags(),
        env=runtime_env(),
    )


def setup_opencode_auth(project_path: str, profile: str) -> tuple[bool, str]:
    if not opencode_profile_exists(profile):
        result = create_opencode_profile(profile, init=True)
        if result.returncode != 0:
            output = (result.stderr or result.stdout or "opencode-multi create failed").strip()
            return False, output
    open_opencode_auth(project_path, profile)
    return True, profile


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
        env=runtime_env(),
    )


def build_obj_prompt(project: dict | None = None) -> str:
    project_name = "your project"
    project_path = ""
    if isinstance(project, dict):
        project_name = str(project.get("name") or project_name)
        project_path = str(project.get("path") or "")

    path_line = f"\nProject path, if useful: {project_path}" if project_path else ""
    return f"""You are an engineering planning assistant.

Turn the project idea below into an OBJ plan that an autonomous coding loop can execute safely.

Project name: {project_name}{path_line}

Input to analyze:
<paste the project brief, existing README, issue, PRD, or rough notes here>

Return only Markdown with this structure:

# Objective Plan

## OBJ-0 - Repository and privacy safety
- Goal:
- Acceptance criteria:
- Files/directories likely involved:
- Tests/checks:
- Risks:

## OBJ-1 - <short actionable objective>
- Goal:
- Acceptance criteria:
- Files/directories likely involved:
- Tests/checks:
- Risks:

Rules:
- Split the work into small, verifiable objectives.
- Start with privacy, secrets, and destructive-action safeguards when relevant.
- Each OBJ must be independently testable by a coding agent.
- Include exact commands for checks when they are knowable.
- Call out assumptions and blockers explicitly.
- Do not include private secrets, tokens, customer data, or local-only paths unless they were provided intentionally.
- Prefer concrete file-level tasks over broad product wishes.
"""


# =========================================================================
# UI
# =========================================================================


class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config = load_config()
        self.provider_buttons: dict[str, tk.Button] = {}
        self.settings_window: tk.Toplevel | None = None

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
        tk.Button(
            header,
            text="\u2699 Settings",
            bg=PANEL,
            fg=FG,
            activebackground="#2a2f3a",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=10,
            pady=6,
            command=self.open_settings,
        ).pack(side="right")

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
        self.provider_buttons = {}
        for column, (mode, label, color) in enumerate(buttons):
            button = tk.Button(
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
            )
            button.grid(row=2, column=column, sticky="w", padx=(12 if column == 0 else 4), pady=10)
            self.provider_buttons[mode] = button

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
        tk.Button(
            bar,
            text="OBJ prompt",
            bg=PANEL,
            fg=FG,
            activebackground="#2a2f3a",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=12,
            pady=8,
            command=self.open_obj_prompt,
        ).pack(side="right", padx=8)
        tk.Button(
            bar,
            text="Auth status",
            bg=PANEL,
            fg=FG,
            activebackground="#2a2f3a",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=12,
            pady=8,
            command=self.show_auth_status,
        ).pack(side="right", padx=8)
        tk.Button(
            bar,
            text="Setup opencode auth",
            bg=PANEL,
            fg=FG,
            activebackground="#2a2f3a",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=12,
            pady=8,
            command=self.setup_auth,
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

    # -- settings and helper windows -----------------------------------------

    def open_text_window(self, title: str, content: str) -> None:
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("820x560")
        window.minsize(620, 420)
        window.configure(bg=BG)

        text = tk.Text(
            window,
            bg="#0b0d12",
            fg=FG,
            insertbackground=FG,
            font=("Consolas", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground="#222733",
            wrap="word",
        )
        text.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        text.insert("1.0", content)

        bar = tk.Frame(window, bg=BG)
        bar.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(
            bar,
            text="Copy",
            bg=CYAN,
            fg="#06121a",
            activebackground="#0891b2",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            padx=12,
            pady=7,
            command=lambda: self.copy_text(text.get("1.0", "end-1c")),
        ).pack(side="left")

    def copy_text(self, content: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.log("Copied to clipboard.")

    def refresh_provider_buttons(self) -> None:
        labels = {
            "secondary": f"{provider_label('secondary')} only",
            "mixed": f"{provider_label('primary')} + {provider_label('secondary')}",
            "alternate": f"{provider_label('alternate')} only",
            "primary_only": f"{provider_label('primary')} only",
        }
        for mode, text in labels.items():
            button = self.provider_buttons.get(mode)
            if button is not None:
                button.configure(text=text)

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("LoopCode Settings")
        window.geometry("980x560")
        window.minsize(760, 420)
        window.configure(bg=BG)

        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            body,
            text="opencode profile",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        profile_var = tk.StringVar(value=PROFILE_NAME)
        tk.Entry(
            body,
            textvariable=profile_var,
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Segoe UI", 10),
            width=24,
        ).grid(row=1, column=0, sticky="we", pady=(0, 14))

        headers = ("Slot", "Label", "Active model", "Models", "API key env", "API key fallback")
        for column, header in enumerate(headers):
            tk.Label(
                body,
                text=header,
                bg=BG,
                fg=MUTED,
                font=("Segoe UI", 9),
            ).grid(row=2, column=column, sticky="w", padx=(0, 8), pady=(0, 4))

        secrets = load_secret_config()
        rows: dict[str, dict[str, tk.StringVar | tk.Entry | ttk.Combobox]] = {}
        for offset, key in enumerate(PROVIDER_KEYS, start=3):
            provider = PROVIDERS[key]
            label_var = tk.StringVar(value=provider["label"])
            model_var = tk.StringVar(value=provider["model"])
            models_var = tk.StringVar(value=", ".join(provider["models"]))
            env_var = tk.StringVar(value=provider["api_key_env"])

            tk.Label(
                body,
                text=key,
                bg=BG,
                fg=FG,
                font=("Segoe UI", 10, "bold"),
            ).grid(row=offset, column=0, sticky="w", padx=(0, 8), pady=4)
            tk.Entry(
                body,
                textvariable=label_var,
                bg=PANEL,
                fg=FG,
                insertbackground=FG,
                relief="flat",
                width=18,
            ).grid(row=offset, column=1, sticky="we", padx=(0, 8), pady=4)
            combo = ttk.Combobox(
                body,
                textvariable=model_var,
                values=provider["models"],
                width=28,
            )
            combo.grid(row=offset, column=2, sticky="we", padx=(0, 8), pady=4)
            tk.Entry(
                body,
                textvariable=models_var,
                bg=PANEL,
                fg=FG,
                insertbackground=FG,
                relief="flat",
                width=36,
            ).grid(row=offset, column=3, sticky="we", padx=(0, 8), pady=4)
            tk.Entry(
                body,
                textvariable=env_var,
                bg=PANEL,
                fg=FG,
                insertbackground=FG,
                relief="flat",
                width=18,
            ).grid(row=offset, column=4, sticky="we", padx=(0, 8), pady=4)
            key_entry = tk.Entry(
                body,
                bg=PANEL,
                fg=FG,
                insertbackground=FG,
                relief="flat",
                show="*",
                width=22,
            )
            key_entry.grid(row=offset, column=5, sticky="we", padx=(0, 8), pady=4)
            if provider["api_key_env"] in secrets["api_keys"]:
                key_entry.insert(0, "")
                key_entry.configure(fg=CYAN)

            rows[key] = {
                "label": label_var,
                "model": model_var,
                "models": models_var,
                "env": env_var,
                "key_entry": key_entry,
            }

        for column in range(6):
            body.grid_columnconfigure(column, weight=1 if column in (2, 3, 5) else 0)

        bar = tk.Frame(window, bg=BG)
        bar.pack(fill="x", padx=14, pady=(0, 14))

        def save_settings() -> None:
            new_config = copy.deepcopy(PROVIDER_CONFIG)
            new_config["profile_name"] = profile_var.get()
            secret_config = load_secret_config()

            for key, row in rows.items():
                old_env = PROVIDERS[key]["api_key_env"]
                label = str(row["label"].get())
                active_model = str(row["model"].get())
                model_values = [
                    item.strip()
                    for item in str(row["models"].get()).split(",")
                    if item.strip()
                ]
                models = _dedupe_strings([active_model, *model_values])
                env_name = str(row["env"].get()).strip()
                api_key = str(row["key_entry"].get())

                new_config["providers"][key] = {
                    "label": label,
                    "model": active_model,
                    "models": models,
                    "api_key_env": env_name,
                }

                if old_env != env_name and old_env in secret_config["api_keys"]:
                    secret_config["api_keys"][env_name] = secret_config["api_keys"].pop(old_env)
                if api_key:
                    secret_config["api_keys"][env_name] = api_key

            save_provider_config(new_config)
            save_secret_config(secret_config)
            reload_runtime_config()
            self.refresh_provider_buttons()
            self.on_select()
            self.log("Settings saved.")
            window.destroy()

        tk.Button(
            bar,
            text="Save",
            bg=CYAN,
            fg="#06121a",
            activebackground="#0891b2",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=14,
            pady=8,
            command=save_settings,
        ).pack(side="left")
        tk.Button(
            bar,
            text="Cancel",
            bg=PANEL,
            fg=FG,
            activebackground="#2a2f3a",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=12,
            pady=8,
            command=window.destroy,
        ).pack(side="left", padx=8)

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

    def selected_profile(self) -> str | None:
        project = self.selected_project()
        if project is None:
            return None
        profile = project.get("profile")
        if isinstance(profile, str) and profile.strip():
            return profile.strip()
        return project_profile(project["path"])

    def refresh_projects(self) -> None:
        self.listbox.delete(0, tk.END)
        for project in self.projects():
            profile = project.get("profile") or project_profile(project["path"])
            self.listbox.insert(
                tk.END,
                f"  {project['name']:<22}  [{profile}]  {project['path']}",
            )
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

    def setup_auth(self) -> None:
        project = self.selected_project()
        profile = self.selected_profile()
        if project is None or profile is None:
            messagebox.showinfo("LoopCode", "Select a project first.")
            return
        try:
            ok, message = setup_opencode_auth(project["path"], profile)
        except (OSError, subprocess.SubprocessError) as exc:
            ok, message = False, str(exc)
        if not ok:
            messagebox.showerror("LoopCode", f"opencode auth setup failed: {message}")
            self.log(f"opencode auth setup failed: {message}")
            return
        self.log(f"Opened opencode auth for profile '{message}'.")

    def show_auth_status(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            messagebox.showinfo("LoopCode", "Select a project first.")
            return
        try:
            result = opencode_providers_list(profile)
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("LoopCode", f"Auth status failed: {exc}")
            self.log(f"Auth status failed: {exc}")
            return
        output = (result.stdout or result.stderr or "").strip()
        if not output:
            output = f"No provider output for profile '{profile}'."
        self.open_text_window(f"opencode providers - {profile}", output)

    def open_obj_prompt(self) -> None:
        self.open_text_window("OBJ prompt", build_obj_prompt(self.selected_project()))

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
        profile = driver_profile(path) or _slugify_profile_name(name)
        self.projects().append({"name": name, "path": path, "profile": profile})
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
