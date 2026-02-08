"""Tests for the settings module."""

import os
import tempfile
from unittest.mock import patch

import yaml

from src.config.settings import (
    DSMRConfig,
    HomeAssistantConfig,
    HTTPServerConfig,
    LoggingConfig,
    MDNSServerConfig,
    ModbusServerConfig,
    PhaseConfig,
    Settings,
    ShellyConfig,
    TotalsConfig,
    UDPServerConfig,
    load_config,
    _parse_config,
)


class TestShellyConfig:
    """Tests for ShellyConfig."""

    def test_defaults(self):
        """Test default values."""
        config = ShellyConfig()

        assert config.device_id == "shellypro3em-emulator"
        assert config.device_name == "Shelly Pro 3EM Emulator"
        assert config.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_custom_values(self):
        """Test with custom values."""
        config = ShellyConfig(
            device_id="my-device",
            device_name="My Device",
            mac_address="11:22:33:44:55:66",
        )

        assert config.device_id == "my-device"
        assert config.device_name == "My Device"
        assert config.mac_address == "11:22:33:44:55:66"


class TestModbusServerConfig:
    """Tests for ModbusServerConfig."""

    def test_defaults(self):
        """Test default values."""
        config = ModbusServerConfig()

        assert config.enabled is True
        assert config.host == "0.0.0.0"
        assert config.port == 502
        assert config.unit_id == 1


class TestUDPServerConfig:
    """Tests for UDPServerConfig."""

    def test_defaults(self):
        """Test default values."""
        config = UDPServerConfig()

        assert config.enabled is True
        assert config.host == "0.0.0.0"
        assert config.ports == [1010, 2220, 22222]


class TestHTTPServerConfig:
    """Tests for HTTPServerConfig."""

    def test_defaults(self):
        """Test default values."""
        config = HTTPServerConfig()

        assert config.enabled is False
        assert config.host == "0.0.0.0"
        assert config.port == 80


class TestMDNSServerConfig:
    """Tests for MDNSServerConfig."""

    def test_defaults(self):
        """Test default values."""
        config = MDNSServerConfig()

        assert config.enabled is False
        assert config.host == ""


class TestHomeAssistantConfig:
    """Tests for HomeAssistantConfig."""

    def test_defaults(self):
        """Test default values."""
        config = HomeAssistantConfig()

        assert config.url == "http://localhost:8123"
        assert config.token == ""
        assert config.use_https is False
        assert config.verify_ssl is True
        assert config.poll_interval == 2.0
        assert config.timeout == 10.0


class TestPhaseConfig:
    """Tests for PhaseConfig."""

    def test_defaults(self):
        """Test default values."""
        config = PhaseConfig()

        assert config.voltage == ""
        assert config.current == ""
        assert config.power == ""
        assert config.power_returned == ""


class TestTotalsConfig:
    """Tests for TotalsConfig."""

    def test_defaults(self):
        """Test default values."""
        config = TotalsConfig()

        assert config.energy_delivered == ""
        assert config.energy_returned == ""
        assert config.energy_delivered_tariff_1 == ""
        assert config.energy_delivered_tariff_2 == ""
        assert config.energy_returned_tariff_1 == ""
        assert config.energy_returned_tariff_2 == ""


class TestDSMRConfig:
    """Tests for DSMRConfig."""

    def test_defaults(self):
        """Test default values."""
        config = DSMRConfig()

        assert config.auto_discover is True
        assert config.single_phase is None
        assert config.three_phase is None

    def test_set_discovered_entities(self):
        """Test set_discovered_entities method."""
        config = DSMRConfig()

        single = {"power": "sensor.power"}
        three = {
            "phase_a": {"power": "sensor.power_l1"},
            "phase_b": {"power": "sensor.power_l2"},
            "phase_c": {"power": "sensor.power_l3"},
        }
        totals = TotalsConfig(energy_delivered="sensor.energy")

        config.set_discovered_entities(
            single_phase=single,
            three_phase=three,
            totals=totals,
            is_three_phase=True,
        )

        assert config._discovered_single_phase == single
        assert config._discovered_three_phase == three
        assert config._discovered_totals == totals
        assert config._is_discovered_three_phase is True

    def test_get_phase_config_discovered(self):
        """Test get_phase_config with discovered config."""
        config = DSMRConfig(auto_discover=True)
        config.set_discovered_entities(
            single_phase=None,
            three_phase={
                "phase_a": {
                    "voltage": "sensor.v1",
                    "current": "sensor.i1",
                    "power": "sensor.p1",
                    "power_returned": "sensor.pr1",
                },
            },
            totals=TotalsConfig(),
            is_three_phase=True,
        )

        phase = config.get_phase_config("phase_a")

        assert phase.voltage == "sensor.v1"
        assert phase.current == "sensor.i1"
        assert phase.power == "sensor.p1"
        assert phase.power_returned == "sensor.pr1"

    def test_get_phase_config_manual(self):
        """Test get_phase_config with manual config."""
        config = DSMRConfig(
            auto_discover=False,
            three_phase={
                "phase_a": {
                    "power": "sensor.manual_power",
                },
            },
        )

        phase = config.get_phase_config("phase_a")

        assert phase.power == "sensor.manual_power"

    def test_get_phase_config_missing_phase(self):
        """Test get_phase_config for missing phase."""
        config = DSMRConfig(auto_discover=False)

        phase = config.get_phase_config("phase_a")

        assert phase.voltage == ""
        assert phase.power == ""

    def test_get_single_phase_power_discovered(self):
        """Test get_single_phase_power with discovered config."""
        config = DSMRConfig(auto_discover=True)
        config.set_discovered_entities(
            single_phase={"power": "sensor.discovered_power"},
            three_phase=None,
            totals=TotalsConfig(),
            is_three_phase=False,
        )

        power = config.get_single_phase_power()

        assert power == "sensor.discovered_power"

    def test_get_single_phase_power_manual(self):
        """Test get_single_phase_power with manual config."""
        config = DSMRConfig(
            auto_discover=False,
            single_phase={"power": "sensor.manual_power"},
        )

        power = config.get_single_phase_power()

        assert power == "sensor.manual_power"

    def test_get_single_phase_power_none(self):
        """Test get_single_phase_power when not configured."""
        config = DSMRConfig(auto_discover=False)

        power = config.get_single_phase_power()

        assert power == ""

    def test_get_totals_discovered(self):
        """Test get_totals with discovered config."""
        config = DSMRConfig(auto_discover=True)
        discovered_totals = TotalsConfig(energy_delivered="sensor.discovered_energy")
        config.set_discovered_entities(
            single_phase=None,
            three_phase=None,
            totals=discovered_totals,
            is_three_phase=False,
        )

        totals = config.get_totals()

        assert totals.energy_delivered == "sensor.discovered_energy"

    def test_get_totals_manual(self):
        """Test get_totals with manual config."""
        manual_totals = TotalsConfig(energy_delivered="sensor.manual_energy")
        config = DSMRConfig(
            auto_discover=False,
            totals=manual_totals,
        )

        totals = config.get_totals()

        assert totals.energy_delivered == "sensor.manual_energy"

    def test_is_three_phase_discovered(self):
        """Test is_three_phase with discovered config."""
        config = DSMRConfig(auto_discover=True)
        config.set_discovered_entities(
            single_phase=None,
            three_phase={"phase_a": {}},
            totals=TotalsConfig(),
            is_three_phase=True,
        )

        assert config.is_three_phase() is True

    def test_is_three_phase_manual_true(self):
        """Test is_three_phase with manual three-phase config."""
        config = DSMRConfig(
            auto_discover=False,
            three_phase={"phase_a": {}, "phase_b": {}, "phase_c": {}},
        )

        assert config.is_three_phase() is True

    def test_is_three_phase_manual_false(self):
        """Test is_three_phase with manual single-phase config."""
        config = DSMRConfig(
            auto_discover=False,
            single_phase={"power": "sensor.power"},
        )

        assert config.is_three_phase() is False

    def test_is_three_phase_empty(self):
        """Test is_three_phase with empty three_phase dict."""
        config = DSMRConfig(
            auto_discover=False,
            three_phase={},
        )

        assert config.is_three_phase() is False


class TestLoggingConfig:
    """Tests for LoggingConfig."""

    def test_defaults(self):
        """Test default values."""
        config = LoggingConfig()

        assert config.level == "INFO"
        assert "%(asctime)s" in config.format


class TestSettings:
    """Tests for Settings."""

    def test_defaults(self):
        """Test default Settings."""
        settings = Settings()

        assert settings.shelly is not None
        assert settings.servers is not None
        assert settings.homeassistant is not None
        assert settings.dsmr is not None
        assert settings.logging is not None


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_from_file(self):
        """Test loading config from a YAML file."""
        config_data = {
            "shelly": {
                "device_id": "test-device",
                "device_name": "Test Device",
            },
            "servers": {
                "modbus": {"enabled": True, "port": 1502},
                "udp": {"ports": [1010]},
                "http": {"enabled": True, "port": 8080},
                "mdns": {"enabled": True},
            },
            "homeassistant": {
                "url": "http://192.168.1.100:8123",
                "token": "test-token",
            },
            "dsmr": {
                "auto_discover": False,
                "single_phase": {"power": "sensor.power"},
            },
            "logging": {"level": "DEBUG"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            settings = load_config(temp_path)

            assert settings.shelly.device_id == "test-device"
            assert settings.servers.modbus.port == 1502
            assert settings.servers.http.enabled is True
            assert settings.servers.mdns.enabled is True
            assert settings.homeassistant.url == "http://192.168.1.100:8123"
            assert settings.dsmr.auto_discover is False
            assert settings.logging.level == "DEBUG"
        finally:
            os.unlink(temp_path)

    def test_load_config_nonexistent_file(self):
        """Test load_config with non-existent file returns defaults."""
        with patch.dict(os.environ, {"CONFIG_PATH": "/nonexistent/path.yaml"}):
            settings = load_config("/nonexistent/config.yaml")

        # Should return defaults
        assert settings.shelly.device_id == "shellypro3em-emulator"

    def test_load_config_from_env(self):
        """Test load_config uses CONFIG_PATH env var."""
        config_data = {"shelly": {"device_id": "env-device"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            with patch.dict(os.environ, {"CONFIG_PATH": temp_path}):
                settings = load_config()

            assert settings.shelly.device_id == "env-device"
        finally:
            os.unlink(temp_path)

    def test_load_config_empty_file(self):
        """Test load_config with empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name

        try:
            settings = load_config(temp_path)

            # Should return defaults
            assert settings.shelly.device_id == "shellypro3em-emulator"
        finally:
            os.unlink(temp_path)


class TestParseConfig:
    """Tests for _parse_config function."""

    def test_parse_empty_dict(self):
        """Test parsing empty dict."""
        settings = _parse_config({})

        assert settings.shelly.device_id == "shellypro3em-emulator"

    def test_parse_full_config(self):
        """Test parsing full config."""
        data = {
            "shelly": {
                "device_id": "custom-id",
                "device_name": "Custom Name",
                "mac_address": "11:22:33:44:55:66",
            },
            "servers": {
                "modbus": {
                    "enabled": False,
                    "host": "127.0.0.1",
                    "port": 1502,
                    "unit_id": 5,
                },
                "udp": {
                    "enabled": False,
                    "host": "127.0.0.1",
                    "ports": [2010, 3220],
                },
                "http": {
                    "enabled": True,
                    "host": "0.0.0.0",
                    "port": 8080,
                },
                "mdns": {
                    "enabled": True,
                    "host": "192.168.1.100",
                },
            },
            "homeassistant": {
                "url": "https://ha.local:8123",
                "token": "my-token",
                "use_https": True,
                "verify_ssl": False,
                "poll_interval": 5.0,
                "timeout": 30.0,
            },
            "dsmr": {
                "auto_discover": False,
                "single_phase": {"power": "sensor.power"},
                "three_phase": {
                    "phase_a": {"power": "sensor.p1"},
                },
                "totals": {
                    "energy_delivered": "sensor.energy",
                    "energy_returned": "sensor.energy_returned",
                    "energy_delivered_tariff_1": "sensor.t1",
                    "energy_delivered_tariff_2": "sensor.t2",
                    "energy_returned_tariff_1": "sensor.rt1",
                    "energy_returned_tariff_2": "sensor.rt2",
                },
            },
            "logging": {
                "level": "ERROR",
                "format": "%(message)s",
            },
        }

        settings = _parse_config(data)

        assert settings.shelly.device_id == "custom-id"
        assert settings.servers.modbus.enabled is False
        assert settings.servers.modbus.port == 1502
        assert settings.servers.udp.ports == [2010, 3220]
        assert settings.servers.http.port == 8080
        assert settings.servers.mdns.host == "192.168.1.100"
        assert settings.homeassistant.use_https is True
        assert settings.homeassistant.verify_ssl is False
        assert settings.dsmr.auto_discover is False
        assert settings.dsmr.totals.energy_delivered == "sensor.energy"
        assert settings.logging.level == "ERROR"

    def test_parse_partial_config(self):
        """Test parsing partial config uses defaults."""
        data = {
            "shelly": {"device_id": "partial-device"},
            # Missing servers, homeassistant, etc.
        }

        settings = _parse_config(data)

        assert settings.shelly.device_id == "partial-device"
        assert settings.servers.modbus.port == 502  # Default
        assert settings.homeassistant.url == "http://localhost:8123"  # Default
