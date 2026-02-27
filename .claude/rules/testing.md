---
paths:
  - "tests/**/*"
  - "test_*.py"
---

# Testing

## Test runner
- **pytest** with asyncio mode: `auto` (no `@pytest.mark.asyncio` needed)
- Config in `pytest.ini` — testpaths=`tests`, `--strict-markers`, `--tb=short`

## Test commands
- All tests: `pytest`
- With coverage: `pytest --cov=src --cov-report=html`
- Modbus only: `pytest -m modbus`
- UDP only: `pytest -m udp`
- Unit only: `pytest -m unit`

## Available markers
`unit`, `integration`, `modbus`, `udp`, `asyncio`

## HTTP mocking
- Use `pytest-httpx` (`httpx_mock` fixture) for mocking Home Assistant REST calls
- All HA client code uses `httpx.AsyncClient`

## Fixtures
- Shared fixtures in `tests/conftest.py`
- Test files mirror `src/` layout: `tests/test_<module>.py`

## Coverage
- Target: `src/` package only
- Run after changes: `pytest --cov=src --cov-report=term-missing`
