"""Integration tests for the complete emulator."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.config import Settings
from src.config.settings import (
    DSMRConfig,
    HomeAssistantConfig,
    ModbusServerConfig,
    ServersConfig,
    ShellyConfig,
    UDPServerConfig,
)
from src.emulator import DataManager, MeterData, PhaseData, ShellyDevice
from src.servers import ModbusServer, UDPServer

from .conftest import registers_to_float


class TestEmulatorIntegration:
    """Integration tests for the complete emulator stack.

    These tests verify that Modbus and UDP servers return consistent data
    by testing the server logic directly without real network operations.
    """

    @pytest.fixture
    def integration_settings(self) -> Settings:
        """Create settings for integration testing."""
        return Settings(
            shelly=ShellyConfig(
                device_id="integration-test",
                device_name="Integration Test Emulator",
                mac_address="11:22:33:44:55:66",
            ),
            servers=ServersConfig(
                modbus=ModbusServerConfig(
                    enabled=True,
                    host="127.0.0.1",
                    port=15503,
                    unit_id=1,
                ),
                udp=UDPServerConfig(
                    enabled=True,
                    host="127.0.0.1",
                    ports=[15012],
                ),
            ),
            homeassistant=HomeAssistantConfig(
                url="http://localhost:8123",
                token="test-token",
                poll_interval=0.5,
            ),
            dsmr=DSMRConfig(
                auto_discover=False,
                three_phase={
                    "phase_a": {"power": "sensor.power_l1"},
                    "phase_b": {"power": "sensor.power_l2"},
                    "phase_c": {"power": "sensor.power_l3"},
                },
            ),
        )

    @pytest.fixture
    def mock_ha_responses(self):
        """Create mock Home Assistant responses."""
        responses = {
            "sensor.power_l1": 1000.0,
            "sensor.power_l2": 800.0,
            "sensor.power_l3": 600.0,
        }
        return responses

    @pytest.fixture
    def emulator_components(self, integration_settings, mock_ha_responses):
        """Create emulator components for testing (without network binding)."""
        # Create device
        device = ShellyDevice(
            device_id=integration_settings.shelly.device_id,
            device_name=integration_settings.shelly.device_name,
            mac_address=integration_settings.shelly.mac_address,
        )

        # Create mock data manager that returns test data
        data_manager = MagicMock(spec=DataManager)
        test_data = MeterData(
            phase_a=PhaseData(
                power=mock_ha_responses["sensor.power_l1"], voltage=230.0
            ),
            phase_b=PhaseData(
                power=mock_ha_responses["sensor.power_l2"], voltage=231.0
            ),
            phase_c=PhaseData(
                power=mock_ha_responses["sensor.power_l3"], voltage=229.0
            ),
            total_energy=4000.0,
            total_energy_returned=10.0,
            timestamp=time.time(),
            is_valid=True,
        )
        data_manager.get_data.return_value = test_data

        # Create servers without starting them
        modbus_server = ModbusServer(
            device=device,
            data_manager=data_manager,
            host=integration_settings.servers.modbus.host,
            port=integration_settings.servers.modbus.port,
            unit_id=integration_settings.servers.modbus.unit_id,
        )

        udp_server = UDPServer(
            device=device,
            data_manager=data_manager,
            host=integration_settings.servers.udp.host,
            ports=integration_settings.servers.udp.ports,
        )

        return {
            "modbus_server": modbus_server,
            "udp_server": udp_server,
            "data_manager": data_manager,
            "device": device,
            "settings": integration_settings,
            "test_data": test_data,
        }

    def test_modbus_and_udp_same_data(self, emulator_components):
        """Test that Modbus and UDP return consistent data."""
        test_data = emulator_components["test_data"]
        udp_server = emulator_components["udp_server"]
        modbus_server = emulator_components["modbus_server"]

        # Get UDP response via internal method
        udp_request = {"id": 1, "method": "EM.GetStatus", "params": {"id": 0}}
        udp_response = udp_server._process_request(udp_request)
        udp_power = udp_response["result"]["total_act_power"]

        # Get Modbus response via register map
        register_map = modbus_server._register_map
        register_map.set_data(test_data)
        modbus_registers = register_map.read_registers(31013, 2)
        modbus_power = registers_to_float(modbus_registers)

        # Both should return approximately the same total power
        expected_total = test_data.total_power
        assert abs(modbus_power - expected_total) < 5.0
        assert abs(udp_power - expected_total) < 5.0

    def test_multiple_udp_requests(self, emulator_components):
        """Test multiple sequential UDP requests."""
        udp_server = emulator_components["udp_server"]

        responses = []
        for i in range(5):
            request = {"id": i, "method": "EM.GetStatus", "params": {"id": 0}}
            response = udp_server._process_request(request)
            responses.append(response)

        # All responses should be valid
        for i, response in enumerate(responses):
            assert response["id"] == i
            assert "result" in response
            assert "total_act_power" in response["result"]

    def test_modbus_sequential_reads(self, emulator_components):
        """Test multiple sequential Modbus reads."""
        modbus_server = emulator_components["modbus_server"]
        test_data = emulator_components["test_data"]

        register_map = modbus_server._register_map
        register_map.set_data(test_data)

        # Read various registers in sequence
        addresses = [
            (31020, 2, "Phase A voltage"),
            (31040, 2, "Phase B voltage"),
            (31060, 2, "Phase C voltage"),
            (31013, 2, "Total power"),
        ]

        for addr, count, desc in addresses:
            registers = register_map.read_registers(addr, count)
            value = registers_to_float(registers)
            assert value is not None, f"Failed to read {desc}"


class TestDataManagerIntegration:
    """Integration tests for DataManager with mocked Home Assistant."""

    @pytest.fixture
    def dm_settings(self) -> Settings:
        """Create settings for data manager testing."""
        return Settings(
            homeassistant=HomeAssistantConfig(
                url="http://localhost:8123",
                token="test-token",
                poll_interval=0.5,
            ),
            dsmr=DSMRConfig(
                auto_discover=False,
                three_phase={
                    "phase_a": {
                        "voltage": "sensor.voltage_l1",
                        "power": "sensor.power_l1",
                    },
                    "phase_b": {
                        "voltage": "sensor.voltage_l2",
                        "power": "sensor.power_l2",
                    },
                    "phase_c": {
                        "voltage": "sensor.voltage_l3",
                        "power": "sensor.power_l3",
                    },
                },
            ),
        )

    @patch("src.data_sources.homeassistant.HomeAssistantClient.get_entity_with_unit")
    @patch("src.data_sources.homeassistant.HomeAssistantClient.get_value")
    def test_data_manager_fetches_three_phase(
        self, mock_get_value, mock_get_entity, dm_settings
    ):
        """Test DataManager correctly fetches three-phase data."""
        from src.data_sources.homeassistant import EntityValue

        voltage_values = {
            "sensor.voltage_l1": 230.5,
            "sensor.voltage_l2": 231.0,
            "sensor.voltage_l3": 229.5,
        }
        power_values = {
            "sensor.power_l1": 1200.0,
            "sensor.power_l2": 900.0,
            "sensor.power_l3": 700.0,
        }
        mock_get_value.side_effect = lambda entity: voltage_values.get(entity)
        mock_get_entity.side_effect = lambda entity: (
            EntityValue(v, "W", v, "2024-01-01T00:00:00Z")
            if (v := power_values.get(entity)) is not None
            else EntityValue(None, None, None)
        )

        manager = DataManager(dm_settings)
        manager._fetch_data()

        data = manager.get_data()

        assert data.phase_a.voltage == 230.5
        assert data.phase_a.power == 1200.0
        assert data.phase_b.power == 900.0
        assert data.phase_c.power == 700.0
        assert abs(data.total_power - 2800.0) < 1.0

    @patch("src.data_sources.homeassistant.HomeAssistantClient.get_entity_with_unit")
    @patch("src.data_sources.homeassistant.HomeAssistantClient.get_value")
    def test_data_manager_handles_unavailable(
        self, mock_get_value, mock_get_entity, dm_settings
    ):
        """Test DataManager handles unavailable entities."""
        from src.data_sources.homeassistant import EntityValue

        voltage_values = {
            "sensor.voltage_l1": 230.0,
            "sensor.voltage_l2": None,  # Unavailable
            "sensor.voltage_l3": 229.0,
        }
        power_values = {
            "sensor.power_l1": 1000.0,
            "sensor.power_l2": None,  # Unavailable
            "sensor.power_l3": 500.0,
        }
        mock_get_value.side_effect = lambda entity: voltage_values.get(entity)
        mock_get_entity.side_effect = lambda entity: (
            EntityValue(v, "W", v, "2024-01-01T00:00:00Z")
            if (v := power_values.get(entity)) is not None
            else EntityValue(None, None, None)
        )

        manager = DataManager(dm_settings)
        manager._fetch_data()

        data = manager.get_data()

        assert data.phase_a.voltage == 230.0
        assert data.phase_b.voltage == 230.0  # Default
        assert data.phase_a.power == 1000.0
        assert data.phase_b.power == 0.0  # Default
