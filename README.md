# LoopCode

LoopCode is a small Windows desktop launcher for local `opencode-multi` agent-loop
projects. It helps you register projects, connect opencode, choose one AI model
for all agents, rewrite the project's `.opencode` model config, and launch the
project's PowerShell loop driver.

The goal of the project is to make coding automation easier to operate: prepare
clear objectives, choose an AI model, authenticate opencode, and launch repeatable
coding loops from one small desktop app.

The app is intentionally local-first:

- runtime dependencies: Python standard library + Tkinter
- private project list: `config.json` (git-ignored)
- private model catalog overrides: `providers.json` (git-ignored)
- public templates: `config.example.json` and `providers.example.json`
- credentials: handled by opencode, not by LoopCode

## Status

LoopCode is a thin launcher for an existing agent-loop setup. It does not install
`opencode`, install `opencode-multi`, generate complete agent prompts, or run a
hosted backend.

Loop launching is currently Windows-only because it uses PowerShell and opens
each loop in its own console.

LoopCode currently works exclusively with `opencode` and `opencode-multi`.
Support for other loop runners can be added later, but the current driver,
auth, model switching, and launch flow all assume opencode.

## Use With AI Coding Tools

LoopCode is designed to be used alongside an AI coding assistant or coding tool,
for example Codex, Claude Code, opencode itself, or another assistant that can
help you plan, review, and refine coding work.

The recommended workflow is:

1. Use an AI assistant to turn a rough project idea into clear OBJ tasks.
2. Put those objectives into your project loop driver or project state.
3. Use LoopCode to select the project, authenticate its opencode profile, choose
   the model, and launch the loop.
4. Use your AI coding assistant again to review outputs, tighten objectives, or
   debug failed loop cycles.

LoopCode is not a replacement for the coding model. It is the local control
surface that makes opencode-based coding loops easier to run repeatedly.

## How It Works

LoopCode sits above three things you already own:

1. a project folder with a loop driver, usually `auto-sentinel.ps1`
2. an `.opencode/` folder with `opencode.json` and `agents/*.md`
3. opencode credentials and profiles managed by `opencode` / `opencode-multi`

The normal flow is:

1. Add a project folder to LoopCode.
2. Connect your global opencode account with `Connect opencode`.
3. Create or open the project's isolated `opencode-multi` auth with `Project auth`.
4. Pick one model in the dropdown, such as `openai/gpt-5.5` or `anthropic/claude-sonnet-4-5`.
5. Click `Apply model`.
6. Click `Launch loop`.

When you click `Apply model`, LoopCode rewrites existing model fields in:

- `.opencode/opencode.json`
- `.opencode/agents/*.md` frontmatter lines like `model: provider/model-id`

It applies the selected model to every configured agent. It does not create new
agents, write prompts, or store provider API keys.

When you click `Launch loop`, LoopCode opens a new PowerShell console and runs:

```powershell
powershell -NoExit -ExecutionPolicy Bypass -File auto-sentinel.ps1
```

If `Resume (-Resume)` is checked, it appends `-Resume`.

## Requirements

- Windows 10/11
- Python 3.10 or newer with Tkinter
- PowerShell
- `opencode` on `PATH`
- `opencode-multi` on `PATH`
- At least one project that follows the driver contract in
  [docs/driver-contract.md](docs/driver-contract.md)

## Quick Start

1. Copy the examples:

   ```powershell
   Copy-Item config.example.json config.json
   Copy-Item providers.example.json providers.json
   ```

2. Edit `config.json` and point a project at your driver folder.

3. Launch the app:

   ```powershell
   py -3 launcher.py
   ```

   Or double-click `LoopCode.bat`.

4. Click `Connect opencode` to open:

   ```powershell
   opencode providers login
   ```

5. Select a project and click `Project auth`. LoopCode creates the profile if
   needed:

   ```powershell
   opencode-multi create <profile> --init
   ```

   Then it opens:

   ```powershell
   opencode-multi run <profile> providers login
   ```

6. Choose a model from the dropdown and click `Apply model`.

7. Click `Launch loop`.

## Buttons

- `Connect opencode`: opens global opencode provider login.
- `Settings`: edits the default profile and model catalog stored in `providers.json`.
- `Apply model`: writes the selected model into the selected project's `.opencode` files.
- `Project auth`: creates/opens auth for the selected project's `opencode-multi` profile.
- `Auth status`: shows global opencode auth and project profile auth status.
- `OBJ prompt`: shows a reusable prompt for turning a project brief into OBJ tasks.
- `Add project`: registers a local project folder in `config.json`.
- `Remove`: removes the project from LoopCode's local list only.
- `Launch loop`: starts the selected project's PowerShell driver.

## Project Config

`config.json` is local and ignored by git:

```json
{
  "projects": [
    {
      "name": "Example driver project",
      "path": "C:\\path\\to\\LoopCode\\examples\\driver-project",
      "profile": "agentic"
    }
  ]
}
```

The committed default in `launcher.py` is deliberately empty:

```json
{"projects": []}
```

LoopCode chooses the project auth profile in this order:

1. `$profileName = "..."` inside the project's `auto-*.ps1`
2. `profile` in `config.json`
3. `profile_name` in `providers.json`

## Model Config

Model ids and agent names live outside the launcher code. Start with
`providers.example.json`, then keep your real `providers.json` private.

The top selector applies one model to every configured agent. No built-in model
combinations are used.

The default catalog includes popular Models.dev/opencode ids for OpenAI,
Anthropic, DeepSeek, Qwen/Alibaba, Z.ai, Gemini/Google, Grok/xAI, MiniMax,
Xiaomi MiMo, Moonshot/Kimi, and Mistral. You can edit the list in `Settings`.

Minimal `providers.json`:

```json
{
  "profile_name": "agentic",
  "model": "openai/gpt-5.5",
  "models": ["openai/gpt-5.5", "anthropic/claude-sonnet-4-5"],
  "agents": {
    "all": ["lead", "security", "reviewer", "debugger", "coder", "researcher", "tester", "docs"]
  }
}
```

## opencode Auth

LoopCode expects credentials to live in opencode. It never asks for API keys and
does not write `auth.json` itself.

Global auth:

```powershell
opencode providers login
```

Project profile auth:

```powershell
opencode-multi run <profile> providers login
```

Auth status:

```powershell
opencode providers list
opencode-multi run <profile> providers list
```

## Prompts

Click `OBJ prompt` in the app to copy a reusable prompt that asks an AI to
translate a rough project brief into small, testable OBJ tasks for the loop.

More reusable prompts are available in [docs/prompts.md](docs/prompts.md),
including prompts for creating OBJ plans, checking loop readiness, drafting a
driver contract, debugging failed cycles, and auditing privacy before publishing.

## Example Driver

`examples/driver-project` is a tiny project that exercises the launcher contract
without depending on private infrastructure. It includes:

- `auto-sentinel.ps1`
- `.opencode/opencode.json`
- `.opencode/agents/*.md`
- `.ai/STATE.json`

The example driver only prints its inputs and runs `self_improve.py`; replace it
with your real loop driver in production.

## Safety Notes

- Do not make a private launcher repo public if it has private paths or commits
  in history.
- Do not commit `config.json` or `providers.json`.
- LoopCode edits `.opencode` files in the selected project. If that project is a
  git repo, model switches may appear as normal git changes.
- LoopCode does not store API keys.

## Tests

Run the standard-library test suite:

```powershell
py -3 -m unittest
```

Optional developer checks:

```powershell
py -3 -m pip install -e .[dev]
ruff check .
pytest
```

## Build

PyInstaller is optional and not needed at runtime:

```powershell
py -3 -m pip install -e .[build]
py -3 -m PyInstaller --onefile --windowed --name "LoopCode" launcher.py
```
