# Shelly Pro 3EM Emulator
Python application that emulates a Shelly Pro 3EM energy meter for Marstek home batteries, reading data from Home Assistant's DSMR integration and exposing it via Modbus TCP, UDP JSON-RPC, HTTP/WebSocket, and mDNS.

## Commands
- Run: `python -m src.main -c config/config.yaml`
- Tests: `pytest`
- Tests with coverage: `pytest --cov=src --cov-report=html`
- Lint: `ruff check src/ tests/`
- Format: `ruff format src/ tests/`
- Type check: `python -m mypy src/`
- Pre-commit: `pre-commit run --all-files`
- Validate emulator: `python tools/validate_emulator.py`
- Bump version: `bump-my-version bump patch` (updates `src/__init__.py` and `addon/config.yaml`)

## Structure
- `src/` — application source
  - `main.py` — entry point, config loading, service orchestration
  - `emulator/` — core: `shelly_device.py` (state), `data_manager.py` (sync), `register_map.py` (Modbus map)
  - `servers/` — `modbus_server.py` (port 502), `udp_server.py` (ports 1010/2220), `http_server.py` (HTTP+WebSocket), `mdns_server.py`
  - `data_sources/` — `homeassistant.py` (HA REST client), `dsmr_discovery.py` (auto-discovery)
  - `config/` — settings/config models
- `tests/` — pytest tests mirroring `src/` layout
- `addon/` — Home Assistant add-on files (`config.yaml`, `run.sh`)
- `docker/` — Docker Compose for standalone deployment
- `tools/` — `validate_emulator.py` standalone validation script
- `config/` — config files (`config.example.yaml`)

## Key conventions
- Python 3.13, async/await throughout (FastAPI + asyncio)
- `structlog` for logging (not standard `logging`)
- Config via YAML (`config/config.yaml`); secrets never committed
- Version lives in `src/__init__.py` and `addon/config.yaml`
- Modbus registers: device info 30000–30099, EM 31000–31079, EMData 31160–31229

## Compaction: always preserve
- List of modified files
- Test error messages and tracebacks
- Current version and active branch
