# Useful Prompts

These prompts are meant to be used with an AI coding assistant such as Codex,
Claude Code, opencode, or another tool that helps plan and review coding work.
LoopCode currently launches opencode-based loops only; these prompts help you
prepare better inputs for those loops.

## Project Brief To OBJ Plan

Use this before launching a loop when you have a rough idea, README, issue, PRD,
or feature request.

```text
You are an engineering planning assistant.

Turn the project idea below into an OBJ plan that an autonomous coding loop can execute safely.

Project name: <project name>

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
```

## Loop Readiness Check

Use this before running a long coding loop.

```text
You are reviewing whether this project is ready for an autonomous coding loop.

Project context:
<paste README, config notes, relevant file tree, and current goal>

Check:
- Is the objective specific enough?
- Are acceptance criteria testable?
- Are required commands known?
- Are secrets, private paths, or destructive operations protected?
- Are there missing driver files such as auto-sentinel.ps1, .opencode/, or .ai/?
- What should be fixed before launching the loop?

Return:
1. Ready / Not ready
2. Blocking issues
3. Suggested OBJ plan
4. Exact checks to run
```

## Driver Contract Builder

Use this when adapting a project so LoopCode can launch it.

```text
You are helping adapt a repository to the LoopCode driver contract.

Repository context:
<paste file tree, README, scripts, and existing automation>

LoopCode expects:
- auto-sentinel.ps1 at the project root
- .opencode/opencode.json
- .opencode/agents/*.md
- .ai/STATE.json
- .ai/reports/
- an opencode-multi profile name, preferably in $profileName

Produce:
- the missing files/directories
- a minimal safe auto-sentinel.ps1 outline
- the expected profile name
- a validation checklist
- risks or assumptions
```

## Failed Cycle Debug

Use this when a loop fails or keeps repairing the same issue.

```text
You are debugging an autonomous coding loop failure.

Inputs:
- Current OBJ:
<paste objective>
- Last terminal output:
<paste logs>
- .ai/STATE.json:
<paste state>
- Recent report or error signature:
<paste report>

Find:
- likely root cause
- whether the objective is too broad or ambiguous
- files likely responsible
- one minimal repair OBJ
- exact test/check command to confirm the fix

Avoid:
- broad rewrites
- changing unrelated files
- retrying the same action without a new guardrail
```

## Privacy Audit Before Publishing

Use this before publishing a launcher, driver, or example project.

```text
You are doing a privacy and open-source readiness audit.

Repository context:
<paste file tree, git status, README, config files, and suspicious grep output>

Check for:
- hardcoded user names
- private local paths
- API keys or tokens
- customer or project names that should stay private
- config files that should be ignored
- generated build artifacts
- git history risks

Return:
- blocking leaks
- non-blocking cleanup
- suggested .gitignore changes
- files safe to publish
- files that must stay private
```

## Objective Tightener

Use this when an OBJ is too vague for an autonomous loop.

```text
Rewrite the objective below so a coding agent can execute it safely.

Objective:
<paste current objective>

Return:
- one sharper OBJ title
- scope boundaries
- acceptance criteria
- files likely involved
- commands/tests
- explicit non-goals
- likely failure modes
```
