# EGARCH 2026 Agent Instructions

This repository implements the EGARCH Forecast Service V1.

Primary spec:

- `docs/superpowers/specs/2026-06-24-egarch-service-design.md`

Linear project:

- `EGARCH Forecast Service V1`
- Delivery issues: `JUL-63` through `JUL-74`

## Working Rules

- Keep changes scoped to the issue being implemented.
- Use tests first for production behavior.
- Keep HTTP routes thin. Business logic belongs in service/domain modules.
- Do not call live Yahoo Finance from default tests.
- Live provider checks must be opt-in and clearly marked.
- Preserve strict T-1 freshness semantics from the spec.
- Do not add trading recommendation language.

## Local Setup

Use Python 3.11 or newer.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Verification Commands

Run these before claiming completion:

```bash
python -m pytest
python -m ruff check .
python -m mypy egarch_service
```

Start the local API:

```bash
python -m uvicorn egarch_service.main:app --reload
```

## Codex Cloud Setup Script

Use this setup script in the Codex Cloud environment:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Agent internet access can stay off for default implementation and test tasks.
Enable internet only for explicit live-provider smoke testing or dependency updates.
