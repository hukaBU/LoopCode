# LoopCode

LoopCode is a small Windows desktop app for managing local agent-loop projects.
It stores a local project list, launches a project's PowerShell driver in a new console,
and switches configured agent model ids across `.opencode` files.

The app is intentionally local-first:

- runtime dependencies: Python standard library + Tkinter
- private project list: `config.json` (git-ignored)
- private provider overrides: `providers.json` (git-ignored)
- optional API-key fallback: `secrets.json` (git-ignored)
- public templates: `config.example.json` and `providers.example.json`

## Status

This is a thin launcher for an existing agent-loop setup. It does not install
`opencode-multi`, create provider accounts, or generate full agent prompts.

Loop launching is currently Windows-only because it uses PowerShell and
`subprocess.CREATE_NEW_CONSOLE`. The config editing helpers are plain Python.

## Requirements

- Windows 10/11
- Python 3.10 or newer with Tkinter
- PowerShell
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

3. Edit `providers.json` for your provider labels, model ids, agent groups, and fallbacks.

4. Launch the app:

   ```powershell
   py -3 launcher.py
   ```

   Or double-click `LoopCode.bat`.

5. Select a project and click `Setup opencode auth`. LoopCode creates the
   `opencode-multi` profile when needed, then opens `opencode providers login`
   through that profile.

## Project Config

`config.json` is local and ignored by git:

```json
{
  "projects": [
    {
      "name": "Example driver project",
      "path": "C:\\path\\to\\LoopCode\\examples\\driver-project"
    }
  ]
}
```

The committed default in `launcher.py` is deliberately empty:

```json
{"projects": []}
```

## Provider Config

Provider ids and agent names live outside the launcher code. Start with
`providers.example.json`, then keep your real `providers.json` private.

The default provider modes are:

- secondary only
- primary + secondary
- alternate only
- primary only

Each mode rewrites existing `model` fields in `.opencode/opencode.json` and
`model:` frontmatter lines in `.opencode/agents/*.md`.

Use `Settings` to choose the active model from each provider slot's dropdown.
The model lists are stored in private `providers.json`.

## opencode Auth

LoopCode expects credentials to live in opencode whenever possible. For each
project, the app uses this profile order:

- `$profileName = "..."` in the project's `auto-*.ps1`
- optional `profile` in `config.json`
- `profile_name` from `providers.json`

`Setup opencode auth` creates the profile with `opencode-multi create <profile>
--init` if it does not exist, then opens:

```powershell
opencode-multi run <profile> providers login
```

`Auth status` runs:

```powershell
opencode-multi run <profile> providers list
```

`secrets.json` is only a fallback for workflows that still need environment
variables injected into the launched driver process.

## OBJ Prompt

Click `OBJ prompt` to copy a reusable prompt that asks an AI to translate a
rough project brief into small, testable OBJ tasks for the loop.

## Example Driver

`examples/driver-project` is a tiny project that exercises the launcher contract
without depending on private infrastructure. It includes:

- `auto-sentinel.ps1`
- `.opencode/opencode.json`
- `.opencode/agents/*.md`
- `.ai/STATE.json`

The example driver only prints its inputs and runs `self_improve.py`; replace it
with your real loop driver in production.

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

## Publishing Safely

If this project was extracted from a private launcher, do not make the private
repository public. Create a fresh repository from these sanitized files instead:

```powershell
git init
git add .
git commit -m "Initial public release"
```
