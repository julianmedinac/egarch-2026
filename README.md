# EGARCH 2026

FastAPI service for one-day-ahead EGARCH volatility forecasts with T-1 freshness,
Yahoo Finance as the first provider, and an auditable path toward production.

The project is intentionally small at the start, but shaped for cloud execution:
clear agent instructions, deterministic tests, lint/type checks, CI, and a
replaceable provider architecture.

## Current Status

Implemented foundation:

- Python package metadata
- FastAPI app factory
- `GET /health`
- `GET /assets`
- V1 asset registry
- pytest, ruff, mypy configuration
- GitHub Actions workflow
- Codex Cloud setup notes

Design spec:

- `docs/superpowers/specs/2026-06-24-egarch-service-design.md`

GitHub:

- `https://github.com/julianmedinac/egarch-2026`

## Requirements

- Python 3.11+
- pip

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run

```bash
python -m uvicorn egarch_service.main:app --reload
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/assets`

## Verify

```bash
python -m pytest
python -m ruff check .
python -m mypy egarch_service
```

## Codex Cloud Environment

Create a Codex Cloud environment for `julianmedinac/egarch-2026` and use:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Suggested first cloud tasks:

1. Implement `JUL-65` SQLite schema and repository layer.
2. Implement `JUL-64` asset registry and market calendar rules.
3. Implement `JUL-68` EGARCH modeling engine and diagnostics.

The repo includes `AGENTS.md`, so Codex Cloud agents have local instructions and
verification commands at checkout time.
