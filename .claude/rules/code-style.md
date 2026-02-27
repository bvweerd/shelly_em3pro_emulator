---
paths:
  - "**/*.py"
---

# Code Style

## Formatter
- **ruff-format** (not black) — run via `ruff format src/ tests/`
- Line length: 88 (ruff default)

## Linter
- **ruff** — run via `ruff check src/ tests/`
- Auto-fix with `ruff check --fix`

## Type hints
- mypy with `--disallow-incomplete-defs`, `--warn-return-any`, `--no-implicit-optional`
- All public functions must have complete type annotations
- Python 3.13+ syntax (e.g. `X | Y` unions, not `Optional[X]`)

## Logging
- Use `structlog` — import as `import structlog; log = structlog.get_logger()`
- Never use the standard `logging` module directly

## Async
- All I/O operations must use `async def` and `await`
- Never block the event loop with synchronous I/O

## Pre-commit hooks
On commit, these run automatically: `pyupgrade`, `codespell`, `ruff`, `ruff-format`, `mypy`
