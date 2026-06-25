# Codex Cloud Setup

Use this guide to run EGARCH 2026 work in Codex Cloud so local laptop uptime is
not required.

## Repository

`https://github.com/julianmedinac/egarch-2026`

## Environment

In Codex, create a Cloud Environment for this repository.

Setup script:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Maintenance script:

```bash
python -m pip install -e ".[dev]"
```

## Internet Access

Default implementation work should not need agent-phase internet access.

Enable internet only for:

- dependency updates
- live Yahoo Finance smoke checks
- external documentation lookup

## Verification

Ask every cloud task to run:

```bash
python -m pytest
python -m ruff check .
python -m mypy egarch_service
```

## Suggested Prompt Template

```text
Work on Linear issue JUL-XX for julianmedinac/egarch-2026.

Read AGENTS.md and the design spec first.
Keep scope limited to JUL-XX.
Use tests first for production behavior.
Run pytest, ruff, and mypy before final response.
Summarize files changed, verification output, and any blockers.
```
