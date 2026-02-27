# Project Architecture

## Directory structure
```
src/
  main.py              # Entry point: loads config, starts all servers
  __init__.py          # Version: __version__ = "2.0.2"
  config/              # Pydantic/YAML config models
  emulator/
    shelly_device.py   # In-memory Shelly device state (the source of truth)
    data_manager.py    # Syncs HA data into shelly_device on a poll interval
    register_map.py    # Modbus register definitions (30000–31229)
  servers/
    modbus_server.py   # pymodbus server on port 502
    udp_server.py      # JSON-RPC UDP server on ports 1010 and 2220
    http_server.py     # FastAPI HTTP API + WebSocket push notifications
    mdns_server.py     # zeroconf mDNS announcements (Shelly device discovery)
  data_sources/
    homeassistant.py   # httpx async client for HA REST API
    dsmr_discovery.py  # Auto-discovers DSMR entities by name patterns
addon/
  config.yaml          # HA add-on manifest (version must match src/__init__.py)
  run.sh               # Add-on entrypoint
docker/
  docker-compose.yml   # Standalone deployment
tools/
  validate_emulator.py # Standalone script to validate a running emulator
```

## Core data flow
1. `data_manager.py` polls Home Assistant REST API every N seconds
2. Raw HA sensor values are unit-converted (kW→W, kWh→Wh) and stored in `shelly_device.py`
3. All servers (`modbus`, `udp`, `http`) read from `shelly_device` on demand
4. WebSocket clients receive push updates when `shelly_device` state changes

## External dependencies
| Package | Purpose |
|---------|---------|
| `pymodbus` | Modbus TCP server (port 502) |
| `fastapi` + `uvicorn` | HTTP REST API + WebSocket server |
| `httpx` | Async HTTP client for Home Assistant |
| `zeroconf` | mDNS discovery announcements |
| `structlog` | Structured logging |
| `pyyaml` | Config file parsing |

## Protocols implemented
- **Modbus TCP** port 502: registers 30000–30099 (device info), 31000–31079 (EM), 31160–31229 (EMData)
- **UDP JSON-RPC** ports 1010 and 2220: `EM.GetStatus`, `EM1.GetStatus`, `EMData.GetStatus`
- **HTTP** (FastAPI): Shelly Gen2 RPC API endpoints
- **WebSocket**: push state updates
- **mDNS**: announces as Shelly Pro 3EM device

## Versioning
- Single version in `src/__init__.py` (`__version__`) and `addon/config.yaml`
- Use `bump-my-version bump patch|minor|major` to update both atomically
- Releases via git tags (`v2.0.2`) trigger CI Docker builds
