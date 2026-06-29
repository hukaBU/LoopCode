# Driver Contract

LoopCode is a wrapper around a project-owned loop driver. A launchable
project is a folder with the following contract.

## Required Files

```text
project-root/
  auto-sentinel.ps1
  .opencode/
    opencode.json
    agents/
      lead.md
      security.md
      reviewer.md
      debugger.md
      coder.md
      researcher.md
      tester.md
      docs.md
  .ai/
    STATE.json
    reports/
```

## PowerShell Driver

The launcher runs:

```powershell
powershell -NoExit -ExecutionPolicy Bypass -File auto-sentinel.ps1 [-Resume]
```

The driver may define a profile name:

```powershell
$profileName = "agentic"
```

The launcher reads that value from `auto-*.ps1` files so provider availability
checks use the same `opencode-multi` profile as the loop.

If the driver does not define `$profileName`, LoopCode uses the optional
`profile` field in `config.json`, then the default `profile_name` from
`providers.json`.

## opencode Files

The model switch updates existing `model` fields in:

- `.opencode/opencode.json`
- `.opencode/agents/*.md` frontmatter lines like `model: provider/model-id`

The launcher only updates existing model fields. It does not add new agent
definitions or create prompts.

## opencode-multi

`opencode-multi` and `opencode` must be available on `PATH`. LoopCode does not
store API keys. It opens global opencode login with:

```powershell
opencode providers login
```

For project profile auth, LoopCode opens:

```powershell
opencode-multi run <profile> providers login
```

That command delegates credentials to opencode under the selected
`opencode-multi` profile.

## .ai State

`self_improve.py` reads `.ai/STATE.json` and writes:

- `.ai/LESSONS.md`
- `.ai/reports/metrics.jsonl`
- global lessons under `~/.loopcode/`

The helper is deterministic and only records lessons/metrics.
