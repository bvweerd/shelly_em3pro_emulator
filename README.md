# Shelly Pro 3EM Emulator

[![CI](https://github.com/bvweerd/shelly_em3pro_emulator/actions/workflows/ci.yml/badge.svg)](https://github.com/bvweerd/shelly_em3pro_emulator/actions/workflows/ci.yml)
[![Release](https://github.com/bvweerd/shelly_em3pro_emulator/actions/workflows/release.yml/badge.svg)](https://github.com/bvweerd/shelly_em3pro_emulator/actions/workflows/release.yml)
[![Docker Image](https://ghcr-badge.egpl.dev/bvweerd/shelly_em3pro_emulator/latest_tag?trim=major&label=version)](https://github.com/bvweerd/shelly_em3pro_emulator/pkgs/container/shelly_em3pro_emulator)

A Docker container with a Python application that emulates a Shelly Pro 3EM energy meter for Marstek home batteries (Venus A, Jupiter, B2500). The emulator retrieves data from Home Assistant via the DSMR integration and makes it available via Modbus TCP and UDP JSON-RPC protocols.

## Features

- **Automatic DSMR entity discovery** - Automatically finds your DSMR sensors in Home Assistant
- **Multi-protocol support** - Modbus TCP (port 502), UDP JSON-RPC (port 1010/2220), HTTP API, and WebSocket
- **3-phase support** - Full support for three-phase power measurements
- **Shelly Pro 3EM compliant** - Implements all EM and EMData registers and Gen2 RPC API
- **mDNS discovery** - Automatically discoverable by Home Assistant and other Shelly-compatible systems
- **Real-time updates** - WebSocket push notifications for instant state changes
- **Docker ready** - Easy deployment via Docker container
- **Home Assistant Add-on** - Install directly from the HA UI, no manual token or config needed

## Quick Start

### Option A: Home Assistant Add-on (easiest)

1. Open Home Assistant → **Settings** → **Add-ons** → ⋮ → **Repositories**
2. Add `https://github.com/bvweerd/shelly_em3pro_emulator`
3. Find **Shelly Pro 3EM Emulator** in the add-on store and install it
4. Configure via the add-on UI (log level, poll interval, auto-discover)
5. Start the add-on

Authentication and the Home Assistant URL are configured automatically via the Supervisor — no long-lived token required.

---

### Option B: Docker (standalone)

#### 1. Configuration

Copy the example configuration file:

```bash
cp config/config.example.yaml config/config.yaml
```

Adjust the configuration with your Home Assistant details:

```yaml
homeassistant:
  url: "http://192.168.1.100:8123"
  token: "YOUR_LONG_LIVED_ACCESS_TOKEN"

dsmr:
  # Auto-discovery is enabled by default
  auto_discover: true
```

#### 2. Create Home Assistant Token

1. Go to your Home Assistant profile (click on your name in the bottom left)
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Give it a name (e.g., "Shelly Emulator") and copy the token

#### 3. Start with Docker

**Option A: Use the pre-built image (recommended)**

Create a directory with your `config.yaml` and `docker-compose.yml`:

```bash
mkdir shelly-emulator && cd shelly-emulator

# Download the example files
curl -O https://raw.githubusercontent.com/bvweerd/shelly-emulator/main/docker-compose.example.yml
curl -O https://raw.githubusercontent.com/bvweerd/shelly-emulator/main/config.example.yaml
cp docker-compose.example.yml docker-compose.yml
cp config.example.yaml config.yaml

# Edit config.yaml with your Home Assistant details
nano config.yaml

# Start the emulator
docker compose up -d
```

Your directory structure should look like:
```
shelly-emulator/
├── docker-compose.yml
└── config.yaml          # Your configuration (required!)
```

**Option B: Build from source**

```bash
git clone https://github.com/bvweerd/shelly-emulator.git
cd shelly-emulator
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml with your settings
cd docker
docker compose up -d --build
```

**Option C: Run with docker directly**

```bash
docker run -d --network host \
  -v /path/to/your/config.yaml:/app/config/config.yaml:ro \
  ghcr.io/bvweerd/shelly-emulator:latest
```

#### 4. Start without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Start the emulator
python -m src.main -c config/config.yaml
```

## Configuration

### Automatic Discovery (recommended)

By default, the emulator automatically searches for DSMR sensors in Home Assistant:

```yaml
dsmr:
  auto_discover: true
```

The emulator looks for entities that match DSMR patterns such as:
- `sensor.*instantaneous_active_power_l1_positive*` (consumption phase 1)
- `sensor.*instantaneous_active_power_l1_negative*` (return phase 1)
- `sensor.*instantaneous_current_l1*` (current phase 1)
- `sensor.*power_consumption*` (total consumption)
- `sensor.*electricity_used_tariff_1*` (energy tariff 1)

**Unit conversion**: Values in kW are automatically converted to W, kWh to Wh.

**Missing data**: Dutch smart meters often do not provide voltage per phase. The emulator then uses 230V as a default value.

### Manual configuration

If auto-discovery does not work, you can configure entities manually:

```yaml
dsmr:
  auto_discover: false

  # Single phase
  single_phase:
    power: "sensor.electricity_meter_power_consumption"

  # Or three-phase
  three_phase:
    phase_a:
      voltage: "sensor.electricity_meter_voltage_phase_l1"
      current: "sensor.electricity_meter_current_phase_l1"
      power: "sensor.electricity_meter_power_consumption_phase_l1"
      power_returned: "sensor.electricity_meter_power_production_phase_l1"
    phase_b:
      # ... same for phase B
    phase_c:
      # ... same for phase C
```

## Protocols

### Modbus TCP (port 502)

The emulator implements the following Modbus registers in accordance with the [Shelly Pro 3EM specification](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM/):

| Register | Type | Description |
|---|---|---|
| 30000-30005 | uint16 | MAC address |
| 30006-30015 | string | Device model |
| 31000-31001 | uint32 | Timestamp |
| 31013-31014 | float | Total active power (W) |
| 31020-31034 | float | Phase A measurements |
| 31040-31054 | float | Phase B measurements |
| 31060-31074 | float | Phase C measurements |
| 31162-31163 | float | Total energy (Wh) |

### UDP JSON-RPC (port 1010/2220)

The emulator responds to JSON-RPC requests:

**EM.GetStatus** - Three-phase power measurements:
```json
{
  "id": 1,
  "method": "EM.GetStatus",
  "params": {"id": 0}
}
```

**EM1.GetStatus** - Single-phase total:
```json
{
  "id": 1,
  "method": "EM1.GetStatus",
  "params": {"id": 0}
}
```

## Marstek Configuration

After starting the emulator:

1. Open the Marstek app
2. Go to settings > Energy meter
3. Select "Shelly Pro 3EM"
4. Enter the IP address of the emulator
5. Set the battery to "Self-Adaptation" mode

### Ports per firmware version

| Marstek Firmware | Port |
|---|---|
| B2500 ≤ v224 | 1010 |
| B2500 ≥ v226 | 2220 |
| Venus / Jupiter | 1010 |

### Home Assistant Integration (Testing Only)

> **⚠️ Warning:** The Home Assistant Shelly integration for this emulator is intended for **testing and validation purposes only**. Since the emulator reads data from Home Assistant's DSMR integration and exposes it as a Shelly device, adding the emulator back to Home Assistant creates a data loop (the same data circulating). For production use, connect the emulator directly to your Marstek battery or other energy management system.

The Shelly Pro 3EM Emulator utilizes mDNS (Multicast DNS) to announce its presence on your local network. Home Assistant can automatically discover the emulator as a Shelly device.

To verify the integration (for testing):

1.  **Ensure the emulator is running:** Follow the "Quick Start" instructions to start the emulator using Docker or directly with Python.
2.  **Check Home Assistant for new devices:**
    *   Navigate to **Settings** -> **Devices & Services** in your Home Assistant instance.
    *   Look for a new integration card for "Shelly" or a new device listed under an existing Shelly integration. The emulator should appear with the device name configured in `config.yaml` (e.g., "Shelly Pro 3EM Emulator").
    *   If Home Assistant does not automatically discover it, ensure both Home Assistant and the emulator are on the same local network and that mDNS traffic is not blocked by your router or firewall.
3.  **Inspect the discovered device:** Once discovered, click on the Shelly emulator device to view its entities (e.g., power, voltage, current, energy totals). These entities should reflect the data being provided by the DSMR integration.

## Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# With coverage report
pytest --cov=src --cov-report=html

# Only Modbus register tests
pytest -m modbus

# Only UDP protocol tests
pytest -m udp
```

## Emulator Validation

There is a standalone validation script to test a running emulator against the Shelly Pro 3EM specification:

```bash
# Validate local emulator (default ports)
python tools/validate_emulator.py

# Validate remote emulator
python tools/validate_emulator.py --host 192.168.1.100

# Test only Modbus
python tools/validate_emulator.py --skip-udp

# Test only UDP
python tools/validate_emulator.py --skip-modbus

# Custom ports
python tools/validate_emulator.py --host localhost --modbus-port 502 --udp-port 1010
```

The script tests:
- **Device Info registers** (30000-30099): MAC, model, name
- **EM registers** (31000-31079): Voltage, current, power per phase
- **EMData registers** (31160-31229): Energy totals
- **UDP JSON-RPC**: EM.GetStatus and EM1.GetStatus responses

Output example:
```
============================================================
MODBUS TCP VALIDATION
============================================================
Connected to Modbus server at localhost:502

--- EM Registers (31000-31079) ---
  [PASS] 31020: Phase A voltage: 230.00 V
  [PASS] 31024: Phase A active power: 1150.00 W
  [WARN] 31028: Phase A power factor: 0.00 (below min -1)
  ...

============================================================
SUMMARY
============================================================
  Total tests: 45
  PASS: 42
  FAIL: 0
  WARN: 3

Validation PASSED with warnings
```

## Compatibility

### Tested Smart Meters

The following table shows tested combinations of smart meters, DSMR versions, and energy management devices. Please report your results via GitHub Issues to help expand this list.

| Smart Meter | DSMR Version | Country | Energy Device | Status | Notes |
|-------------|--------------|---------|---------------|--------|-------|
| - | 5.0 | NL | Marstek Venus | ❓ Untested | |
| - | 5.0 | NL | Marstek Jupiter | ❓ Untested | |
| - | 5.0 | NL | Marstek B2500 | ❓ Untested | |
| - | 4.2 | NL | Marstek Venus | ❓ Untested | |
| - | 4.0 | BE | Marstek Venus | ❓ Untested | Belgian meters |
| - | 5.0 | NL | Home Assistant | ✅ Tested | Testing only |

**Status legend:**
- ✅ Tested and working
- ⚠️ Tested with limitations
- ❌ Not working
- ❓ Untested

### DSMR Version Support

| DSMR Version | Support | Country | Notes |
|--------------|---------|---------|-------|
| 5.0 / 5.0.2 | ✅ Full | NL | Dutch standard, full 3-phase power data |
| 4.2 / 4.2.3 | ✅ Full | NL | Dutch standard, 3-phase power data |
| 4.0.7 | ⚠️ Partial | BE | Belgian Fluvius meters, different entity names |
| 4.0 | ⚠️ Partial | LU | Luxembourg meters |
| 2.2 - 3.0 | ❓ Unknown | NL | Legacy meters (limited data) |

## DSMR Technical Reference

### OBIS Codes

The emulator supports all standard DSMR electricity OBIS codes. These codes identify specific measurements in the P1 telegram:

#### Instantaneous Power (Real-time)

| OBIS Code | Description | HA Entity Pattern | Unit |
|-----------|-------------|-------------------|------|
| 1-0:1.7.0 | Total power consumption | `*power_consumption`, `*power_delivered` | kW |
| 1-0:2.7.0 | Total power production | `*power_production`, `*power_returned` | kW |
| 1-0:21.7.0 | Power consumption L1 | `*power_delivered_l1`, `*power_l1_positive` | kW |
| 1-0:22.7.0 | Power production L1 | `*power_returned_l1`, `*power_l1_negative` | kW |
| 1-0:41.7.0 | Power consumption L2 | `*power_delivered_l2`, `*power_l2_positive` | kW |
| 1-0:42.7.0 | Power production L2 | `*power_returned_l2`, `*power_l2_negative` | kW |
| 1-0:61.7.0 | Power consumption L3 | `*power_delivered_l3`, `*power_l3_positive` | kW |
| 1-0:62.7.0 | Power production L3 | `*power_returned_l3`, `*power_l3_negative` | kW |

#### Instantaneous Current & Voltage

| OBIS Code | Description | HA Entity Pattern | Unit | Note |
|-----------|-------------|-------------------|------|------|
| 1-0:31.7.0 | Current L1 | `*current_l1`, `*instantaneous_current_l1` | A | |
| 1-0:51.7.0 | Current L2 | `*current_l2`, `*instantaneous_current_l2` | A | |
| 1-0:71.7.0 | Current L3 | `*current_l3`, `*instantaneous_current_l3` | A | |
| 1-0:32.7.0 | Voltage L1 | `*voltage_l1`, `*instantaneous_voltage_l1` | V | Often unavailable* |
| 1-0:52.7.0 | Voltage L2 | `*voltage_l2`, `*instantaneous_voltage_l2` | V | Often unavailable* |
| 1-0:72.7.0 | Voltage L3 | `*voltage_l3`, `*instantaneous_voltage_l3` | V | Often unavailable* |

*\* Voltage is not available on all Dutch smart meters. The emulator uses 230V as default.*

#### Energy Totals (Cumulative)

| OBIS Code | Description | HA Entity Pattern | Unit |
|-----------|-------------|-------------------|------|
| 1-0:1.8.1 | Energy consumption tariff 1 (low) | `*energy_consumption*tariff*1`, `*electricity_used_tariff_1` | kWh |
| 1-0:1.8.2 | Energy consumption tariff 2 (normal) | `*energy_consumption*tariff*2`, `*electricity_used_tariff_2` | kWh |
| 1-0:2.8.1 | Energy production tariff 1 (low) | `*energy_production*tariff*1`, `*electricity_delivered_tariff_1` | kWh |
| 1-0:2.8.2 | Energy production tariff 2 (normal) | `*energy_production*tariff*2`, `*electricity_delivered_tariff_2` | kWh |

### Dutch Tariff System

Dutch smart meters use two tariffs:
- **Tariff 1 (Low/Dal)**: Nights (23:00-07:00) and weekends
- **Tariff 2 (Normal/Piek)**: Daytime on weekdays (07:00-23:00)

The emulator sums both tariffs for total energy when no explicit total entity is available.

### Data Availability by DSMR Version

| Data | DSMR 5.0 | DSMR 4.2 | DSMR 4.0 (BE) | Notes |
|------|----------|----------|---------------|-------|
| Power per phase (L1/L2/L3) | ✅ | ✅ | ✅ | Always available |
| Current per phase | ✅ | ✅ | ✅ | Always available |
| Voltage per phase | ⚠️ | ⚠️ | ⚠️ | Meter firmware dependent |
| Energy per tariff | ✅ | ✅ | ✅ | Always available |
| Gas meter reading | ✅ | ✅ | ✅ | M-Bus device, not used |
| Power failures/sags | ✅ | ✅ | ❌ | Not used by emulator |

### DSMR Data Limitations

Dutch smart meters (P1 port) do not provide all the data that a Shelly Pro 3EM normally does:

| Data | DSMR Available | Shelly Register | Solution |
|------|----------------|-----------------|----------|
| Power per phase | ✅ Yes (kW) | Yes | Automatic conversion kW → W |
| Current per phase | ✅ Yes (A) | Yes | Directly available |
| Voltage per phase | ⚠️ Sometimes | Yes | Default: 230V when unavailable |
| Frequency | ❌ No | Yes | Default: 50Hz |
| Power factor | ❌ No | Yes | Calculated: \|P\| / (V × I) |
| Apparent power | ❌ No | Yes | Calculated: V × I |
| Energy totals | ✅ Yes (kWh) | Yes | Sum of tariff 1 + tariff 2 |

The emulator calculates missing values where possible and uses realistic defaults for the rest.

### Unit Conversions

The emulator automatically converts units from Home Assistant DSMR integration:

| Source Unit | Target Unit | Conversion |
|-------------|-------------|------------|
| kW | W | × 1000 |
| MW | W | × 1000000 |
| kWh | Wh | × 1000 |
| MWh | Wh | × 1000000 |

### Regional Entity Name Patterns

The auto-discovery supports multiple naming conventions:

| Region | Language | Example Entity Patterns |
|--------|----------|------------------------|
| Netherlands | English | `sensor.electricity_meter_power_consumption` |
| Netherlands | Dutch | `sensor.elektriciteit_vermogen`, `sensor.energie_dal` |
| Belgium | Fluvius | `sensor.fluvius_consumption`, `sensor.fluvius_production` |
| Luxembourg | French | `sensor.electricite_puissance`, `sensor.courant_l1` |

## Troubleshooting

### Emulator does not start

- Check if ports 502, 1010, 2220 are free
- With Docker: use `network_mode: host` for UDP broadcast support

### Marstek does not find emulator

- Make sure both devices are on the same subnet
- Check firewall rules for UDP ports
- Try disconnecting Bluetooth during setup

### No data from Home Assistant

- Test the token with: `curl -H "Authorization: Bearer TOKEN" http://HA_IP:8123/api/`
- Check if DSMR integration is active in Home Assistant
- Check the logs with `docker logs shelly-emulator`

### Auto-discovery finds no entities

- Check entity names in Home Assistant Developer Tools > States
- Try manual configuration if names differ from standard patterns

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Docker Container                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                 Shelly Pro 3EM Emulator                    │  │
│  │                                                            │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │  │
│  │  │  Modbus  │ │   UDP    │ │   HTTP   │ │    mDNS      │  │  │
│  │  │  Server  │ │  Server  │ │ Server + │ │  Discovery   │  │  │
│  │  │  (502)   │ │(1010/2220│ │ WebSocket│ │              │  │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────────┘  │  │
│  │       └────────────┴────────────┘                         │  │
│  │                     │                                     │  │
│  │            ┌────────▼────────┐    ┌──────────────────┐    │  │
│  │            │  Data Manager   │◄───│  Home Assistant  │    │  │
│  │            │  (cache/sync)   │    │   Data Fetcher   │    │  │
│  │            └─────────────────┘    └──────────────────┘    │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
         │              │               │
         ▼              ▼               ▼
┌─────────────────┐  ┌────────┐  ┌─────────────────────┐
│  Marstek Venus  │  │ Other  │  │   Home Assistant    │
│  Jupiter/B2500  │  │ Devices│  │  (DSMR integration) │
│  (home battery) │  │        │  │    [data source]    │
└─────────────────┘  └────────┘  └─────────────────────┘
```

## Releases & Versioning

This project uses [Semantic Versioning](https://semver.org/) (e.g., `v1.0.0`, `v1.1.0`, `v2.0.0`).

### Creating a Release

To create a new release:

```bash
# Tag the release (triggers automatic Docker build & GitHub release)
git tag v1.0.0
git push origin v1.0.0
```

This automatically:
1. Runs all tests
2. Builds multi-platform Docker images (amd64, arm64) for both standalone and add-on
3. Pushes to GitHub Container Registry with version tags
4. Updates `addon/config.yaml` version
5. Creates a GitHub Release with changelog

### Docker Image Tags

**Standalone image** (`ghcr.io/bvweerd/shelly_em3pro_emulator`):

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release |
| `v1.2.3` | Specific version |
| `v1.2` | Latest patch of v1.2.x |
| `v1` | Latest minor/patch of v1.x.x |

**Add-on image** (`ghcr.io/bvweerd/shelly_em3pro_emulator-addon`):

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release |
| `v1.2.3` | Specific version |

```bash
# Pull standalone image
docker pull ghcr.io/bvweerd/shelly_em3pro_emulator:latest

# Add-on image is pulled automatically by Home Assistant
```

## License

MIT License

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/bvweerd/shelly-emulator.git
cd shelly-emulator

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest

# Run linting
black src/ tests/
ruff check src/ tests/
mypy src/
```