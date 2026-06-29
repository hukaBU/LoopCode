# Contributing

Thanks for helping improve LoopCode.

## Local Setup

```powershell
py -3 -m pip install -e .[dev]
py -3 -m unittest
ruff check .
pytest
```

## Privacy Rules

- Do not commit `config.json`.
- Do not commit `providers.json`.
- Do not commit private project paths, customer names, API keys, logs, or build outputs.
- Use `config.example.json` and `providers.example.json` for public examples.

## Pull Requests

Please keep changes small and focused. Include tests when changing provider
selection, file rewriting, or reflection behavior.
