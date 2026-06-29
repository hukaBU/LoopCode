"""LoopCode - desktop helper for opencode-multi projects.

LoopCode keeps a local list of projects, launches each project's PowerShell
driver, helps authenticate opencode profiles, and switches all configured
agents to one selected model.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "config.json"
PROVIDERS_FILE = APP_DIR / "providers.json"
PROVIDERS_EXAMPLE_FILE = APP_DIR / "providers.example.json"

DEFAULT_AGENTS = [
    "lead",
    "security",
    "reviewer",
    "debugger",
    "coder",
    "researcher",
    "tester",
    "docs",
]

POPULAR_MODELS = [
    "openai/gpt-5.5",
    "openai/gpt-5.5-fast",
    "openai/gpt-5.4",
    "openai/gpt-5.4-fast",
    "openai/gpt-5.4-mini",
    "openai/gpt-5.2-pro",
    "openai/gpt-5",
    "openai/gpt-5-pro",
    "openai/gpt-4o",
    "openai/o3",
    "openai/o4-mini",
    "anthropic/claude-opus-4-5",
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-haiku-4-5-20251001",
    "anthropic/claude-opus-4-1",
    "anthropic/claude-3-5-sonnet-20241022",
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-reasoner",
    "deepseek/deepseek-chat",
    "alibaba/qwen3-coder-plus",
    "alibaba/qwen-plus",
    "alibaba/qwen3-max",
    "alibaba/qwen3.7-plus",
    "alibaba-coding-plan/qwen3-coder-plus",
    "alibaba-coding-plan/qwen3.7-max",
    "zai/glm-5.2",
    "zai/glm-5.1",
    "zai/glm-4.7",
    "zai/glm-5-turbo",
    "zai-coding-plan/glm-5.2",
    "zai-coding-plan/glm-5.1",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash",
    "google/gemini-3.5-flash",
    "google-vertex/gemini-2.5-pro",
    "google-vertex/gemini-2.5-flash",
    "xai/grok-4.3",
    "xai/grok-4.20-0309-reasoning",
    "xai/grok-4.20-0309-non-reasoning",
    "xai/grok-build-0.1",
    "minimax/MiniMax-M2.5",
    "minimax/MiniMax-M3",
    "minimax-coding-plan/MiniMax-M2.5",
    "xiaomi/mimo-v2.5-pro",
    "xiaomi/mimo-v2.5",
    "xiaomi/mimo-v2-flash",
    "moonshotai/kimi-k2.7-code",
    "moonshotai/kimi-k2-thinking-turbo",
    "moonshotai/kimi-k2.5",
    "mistral/mistral-large-latest",
    "mistral/codestral-latest",
]

DEFAULT_CONFIG = {"projects": []}
DEFAULT_PROVIDER_CONFIG = {
    "profile_name": "agentic",
    "model": "openai/gpt-5.5",
    "models": POPULAR_MODELS,
    "agents": {"all": DEFAULT_AGENTS},
}

# --- Theme -------------------------------------------------------------------
BG = "#0f1117"
PANEL = "#171a21"
FG = "#e6e8eb"
MUTED = "#8b93a1"
CYAN = "#22d3ee"
RED = "#b91c1c"


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


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _clean_string_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return cleaned or list(fallback)


def _agents_from_raw(raw_agents: object) -> list[str]:
    if not isinstance(raw_agents, dict):
        return list(DEFAULT_AGENTS)
    if isinstance(raw_agents.get("all"), list):
        return _clean_string_list(raw_agents.get("all"), DEFAULT_AGENTS)
    primary = _clean_string_list(raw_agents.get("primary"), [])
    secondary = _clean_string_list(raw_agents.get("secondary"), [])
    return _dedupe_strings([*primary, *secondary]) or list(DEFAULT_AGENTS)


def _models_from_legacy_providers(providers: object) -> list[str]:
    if not isinstance(providers, dict):
        return []
    models: list[str] = []
    for provider in providers.values():
        if not isinstance(provider, dict):
            continue
        model = provider.get("model")
        if isinstance(model, str):
            models.append(model)
        provider_models = provider.get("models")
        if isinstance(provider_models, list):
            models.extend(item for item in provider_models if isinstance(item, str))
    return models


def load_provider_config_from_data(data: dict) -> dict:
    cfg = copy.deepcopy(DEFAULT_PROVIDER_CONFIG)
    raw = data if isinstance(data, dict) else {}

    legacy_models = _models_from_legacy_providers(raw.get("providers"))
    raw_models = raw.get("models")
    models = _clean_string_list(raw_models, POPULAR_MODELS)
    models = _dedupe_strings([*legacy_models, *models])

    default_model = _clean_string(raw.get("model"), models[0])
    if default_model not in models:
        models.insert(0, default_model)

    cfg["profile_name"] = _clean_string(raw.get("profile_name"), cfg["profile_name"])
    cfg["model"] = default_model
    cfg["models"] = models
    cfg["agents"] = {"all": _agents_from_raw(raw.get("agents"))}
    return cfg


def load_provider_config(
    config_path: Path | None = None,
    example_path: Path | None = None,
) -> dict:
    """Load local model settings from providers.json, then providers.example.json."""

    paths = (
        config_path or PROVIDERS_FILE,
        example_path or PROVIDERS_EXAMPLE_FILE,
    )
    for path in paths:
        if path.exists():
            raw = _read_json_file(path)
            if raw is not None:
                return load_provider_config_from_data(raw)
    return copy.deepcopy(DEFAULT_PROVIDER_CONFIG)


def save_provider_config(config: dict, path: Path | None = None) -> None:
    target = path or PROVIDERS_FILE
    cleaned = load_provider_config_from_data(config)
    target.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")


def configure_runtime(config: dict | None = None) -> None:
    global PROVIDER_CONFIG, PROFILE_NAME, DEFAULT_MODEL, MODEL_CATALOG, ALL_AGENTS

    PROVIDER_CONFIG = load_provider_config_from_data(config or load_provider_config())
    PROFILE_NAME = PROVIDER_CONFIG["profile_name"]
    DEFAULT_MODEL = PROVIDER_CONFIG["model"]
    MODEL_CATALOG = tuple(PROVIDER_CONFIG["models"])
    ALL_AGENTS = tuple(PROVIDER_CONFIG["agents"]["all"])


def reload_runtime_config() -> None:
    configure_runtime(load_provider_config())


PROVIDER_CONFIG: dict = {}
PROFILE_NAME = ""
DEFAULT_MODEL = ""
MODEL_CATALOG: tuple[str, ...] = ()
ALL_AGENTS: tuple[str, ...] = ()
configure_runtime()


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


def _windows_console_flags() -> int:
    if not hasattr(subprocess, "CREATE_NEW_CONSOLE"):
        raise OSError("Interactive opencode commands are currently Windows-only.")
    return subprocess.CREATE_NEW_CONSOLE


def _slugify_profile_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or PROFILE_NAME


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
    """Return the opencode-multi profile used by the project."""

    return driver_profile(project_path) or configured_project_profile(project_path) or PROFILE_NAME


def opencode_profile_exists(profile: str) -> bool:
    result = subprocess.run(
        ["opencode-multi", "show", profile],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
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
    )


def opencode_providers_list(profile: str | None = None) -> subprocess.CompletedProcess[str]:
    args = ["opencode-multi", "run", profile, "providers", "list"] if profile else [
        "opencode",
        "providers",
        "list",
    ]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def open_opencode_login(project_path: str | None = None, profile: str | None = None) -> None:
    if profile:
        args = ["opencode-multi", "run", profile, "providers", "login"]
    else:
        args = ["opencode", "providers", "login"]
    subprocess.Popen(
        args,
        cwd=str(project_path or APP_DIR),
        creationflags=_windows_console_flags(),
    )


def setup_project_auth(project_path: str, profile: str) -> tuple[bool, str]:
    if not opencode_profile_exists(profile):
        result = create_opencode_profile(profile, init=True)
        if result.returncode != 0:
            output = (result.stderr or result.stdout or "opencode-multi create failed").strip()
            return False, output
    open_opencode_login(project_path, profile)
    return True, profile


def current_project_model(project_path: str) -> str:
    opencode_dir = Path(project_path) / ".opencode"
    models = [_agent_model(opencode_dir, agent) for agent in ALL_AGENTS]
    models = [model for model in models if model]
    if not models:
        return "unknown"
    unique = set(models)
    return models[0] if len(unique) == 1 else "mixed"


def apply_model(project_path: str, model: str) -> dict[str, str]:
    """Rewrite all configured agents to one selected model."""

    selected = model.strip()
    if not selected:
        raise ValueError("Choose a model first.")

    opencode_dir = Path(project_path) / ".opencode"
    config_file = opencode_dir / "opencode.json"
    if not config_file.exists():
        raise FileNotFoundError(f".opencode/opencode.json not found in {project_path}")

    data = json.loads(config_file.read_text(encoding="utf-8"))
    applied = {agent: selected for agent in ALL_AGENTS}

    for name, agent_cfg in data.get("agent", {}).items():
        if name in applied and isinstance(agent_cfg, dict) and "model" in agent_cfg:
            agent_cfg["model"] = selected
    config_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    for name in ALL_AGENTS:
        md = opencode_dir / "agents" / f"{name}.md"
        if md.exists():
            text = md.read_text(encoding="utf-8")
            new_text = re.sub(r"(?m)^model:.*$", f"model: {selected}", text, count=1)
            if new_text != text:
                md.write_text(new_text, encoding="utf-8")
    return applied


def launch_loop(project_path: str, *, resume: bool = False) -> None:
    """Launch auto-sentinel.ps1 in a new Windows PowerShell console."""

    ps1 = Path(project_path) / "auto-sentinel.ps1"
    if not ps1.exists():
        raise FileNotFoundError(f"auto-sentinel.ps1 not found in {project_path}")
    args = ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(ps1)]
    if resume:
        args.append("-Resume")
    subprocess.Popen(
        args,
        cwd=str(project_path),
        creationflags=_windows_console_flags(),
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
        self.settings_window: tk.Toplevel | None = None

        root.title("LoopCode")
        root.geometry("920x620")
        root.minsize(760, 540)
        root.configure(bg=BG)

        self._build_header()
        self._build_model_panel()
        self._build_projects_panel()
        self._build_actions()
        self._build_log()

        self.refresh_projects()
        self.log("Ready. Connect opencode, select a project, choose one model, then launch.")

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
        tk.Button(
            header,
            text="Connect opencode",
            bg=PANEL,
            fg=FG,
            activebackground="#2a2f3a",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=10,
            pady=6,
            command=self.connect_opencode,
        ).pack(side="right", padx=8)

    def _build_model_panel(self) -> None:
        panel = tk.Frame(self.root, bg=PANEL)
        panel.pack(fill="x", padx=16, pady=6)
        panel.grid_columnconfigure(0, weight=1)

        tk.Label(
            panel,
            text="Single model for all agents:",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 2))

        self.current_model_value = tk.Label(
            panel,
            text="-",
            bg=PANEL,
            fg=FG,
            font=("Segoe UI", 11, "bold"),
        )
        self.current_model_value.grid(row=1, column=0, columnspan=2, sticky="w", padx=12)

        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_combo = ttk.Combobox(
            panel,
            textvariable=self.model_var,
            values=MODEL_CATALOG,
            width=54,
        )
        self.model_combo.grid(row=2, column=0, sticky="we", padx=12, pady=10)
        tk.Button(
            panel,
            text="Apply model",
            bg=CYAN,
            fg="#06121a",
            activebackground="#0891b2",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            padx=12,
            pady=7,
            command=self.apply_selected_model,
        ).grid(row=2, column=1, sticky="e", padx=(0, 12), pady=10)

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

        actions = (
            ("Remove", self.remove_project),
            ("Add project", self.add_project),
            ("OBJ prompt", self.open_obj_prompt),
            ("Auth status", self.show_auth_status),
            ("Project auth", self.setup_project_auth),
        )
        for text, command in actions:
            tk.Button(
                bar,
                text=text,
                bg=PANEL,
                fg=FG,
                activebackground=RED if text == "Remove" else "#2a2f3a",
                activeforeground="white",
                relief="flat",
                font=("Segoe UI", 9),
                cursor="hand2",
                padx=12,
                pady=8,
                command=command,
            ).pack(side="right", padx=4)

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

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("LoopCode Settings")
        window.geometry("820x520")
        window.minsize(640, 420)
        window.configure(bg=BG)

        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(body, text="Default opencode profile", bg=BG, fg=MUTED).pack(anchor="w")
        profile_var = tk.StringVar(value=PROFILE_NAME)
        tk.Entry(
            body,
            textvariable=profile_var,
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Segoe UI", 10),
        ).pack(fill="x", pady=(4, 12))

        tk.Label(body, text="Default model", bg=BG, fg=MUTED).pack(anchor="w")
        default_model_var = tk.StringVar(value=DEFAULT_MODEL)
        ttk.Combobox(
            body,
            textvariable=default_model_var,
            values=MODEL_CATALOG,
        ).pack(fill="x", pady=(4, 12))

        tk.Label(
            body,
            text="Model catalog (one provider/model per line)",
            bg=BG,
            fg=MUTED,
        ).pack(anchor="w")
        models_text = tk.Text(
            body,
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            height=12,
            font=("Consolas", 9),
        )
        models_text.pack(fill="both", expand=True, pady=(4, 12))
        models_text.insert("1.0", "\n".join(MODEL_CATALOG))

        bar = tk.Frame(window, bg=BG)
        bar.pack(fill="x", padx=14, pady=(0, 14))

        def save_settings() -> None:
            models = [
                line.strip()
                for line in models_text.get("1.0", "end").splitlines()
                if line.strip()
            ]
            default_model = default_model_var.get().strip()
            if default_model:
                models = _dedupe_strings([default_model, *models])
            new_config = {
                "profile_name": profile_var.get().strip() or PROFILE_NAME,
                "model": default_model or (models[0] if models else DEFAULT_MODEL),
                "models": models or list(MODEL_CATALOG),
                "agents": {"all": list(ALL_AGENTS)},
            }
            save_provider_config(new_config)
            reload_runtime_config()
            self.model_combo.configure(values=MODEL_CATALOG)
            self.model_var.set(DEFAULT_MODEL)
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
            self.current_model_value.config(text="-")

    def on_select(self) -> None:
        project = self.selected_project()
        if project is None:
            self.current_model_value.config(text="-")
            return
        model = current_project_model(project["path"])
        self.current_model_value.config(text=model)
        if model not in ("unknown", "mixed"):
            self.model_var.set(model)

    def connect_opencode(self) -> None:
        try:
            open_opencode_login()
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("LoopCode", f"opencode login failed: {exc}")
            self.log(f"opencode login failed: {exc}")
            return
        self.log("Opened opencode provider login.")

    def setup_project_auth(self) -> None:
        project = self.selected_project()
        profile = self.selected_profile()
        if project is None or profile is None:
            messagebox.showinfo("LoopCode", "Select a project first.")
            return
        try:
            ok, message = setup_project_auth(project["path"], profile)
        except (OSError, subprocess.SubprocessError) as exc:
            ok, message = False, str(exc)
        if not ok:
            messagebox.showerror("LoopCode", f"Project auth failed: {message}")
            self.log(f"Project auth failed: {message}")
            return
        self.log(f"Opened opencode auth for project profile '{message}'.")

    def show_auth_status(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            messagebox.showinfo("LoopCode", "Select a project first.")
            return
        try:
            global_result = opencode_providers_list()
            project_result = opencode_providers_list(profile)
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("LoopCode", f"Auth status failed: {exc}")
            self.log(f"Auth status failed: {exc}")
            return
        output = [
            "Global opencode credentials:",
            (global_result.stdout or global_result.stderr or "").strip() or "(no output)",
            "",
            f"Project profile '{profile}' credentials:",
            (project_result.stdout or project_result.stderr or "").strip() or "(no output)",
        ]
        self.open_text_window("opencode auth status", "\n".join(output))

    def open_obj_prompt(self) -> None:
        self.open_text_window("OBJ prompt", build_obj_prompt(self.selected_project()))

    def apply_selected_model(self) -> None:
        project = self.selected_project()
        if project is None:
            messagebox.showinfo("LoopCode", "Select a project first.")
            return
        model = self.model_var.get().strip()
        try:
            applied = apply_model(project["path"], model)
        except (OSError, ValueError) as exc:
            messagebox.showerror("LoopCode", f"Model switch failed: {exc}")
            self.log(f"Model switch failed: {exc}")
            return
        self.on_select()
        self.log(f"{project['name']} -> {model} ({len(applied)} agents)")

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
        model = current_project_model(project["path"])
        mode = " (resume)" if self.resume_var.get() else ""
        self.log(f"Loop launched: {project['name']}{mode} - {model}")

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
