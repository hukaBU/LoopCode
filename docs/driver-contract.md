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

## opencode Files

The provider switch updates existing `model` fields in:

- `.opencode/opencode.json`
- `.opencode/agents/*.md` frontmatter lines like `model: provider/model-id`

The launcher only updates existing model fields. It does not add new agent
definitions or create prompts.

## opencode-multi

`opencode-multi` must be available on `PATH`. The launcher checks model
availability with:

```powershell
opencode-multi run <profile> models <provider>
```

If a requested model is unavailable, configured fallbacks from `providers.json`
are tried.

## .ai State

`self_improve.py` reads `.ai/STATE.json` and writes:

- `.ai/LESSONS.md`
- `.ai/reports/metrics.jsonl`
- global lessons under `~/.loopcode/`

The helper is deterministic and only records lessons/metrics.
