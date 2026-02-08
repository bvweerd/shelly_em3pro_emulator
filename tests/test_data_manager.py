"""Tests for the data manager module."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.data_sources.homeassistant import EntityValue
from src.emulator.data_manager import DataManager, MeterData, PhaseData
from src.config import Settings
from src.config.settings import (
    DSMRConfig,
    HomeAssistantConfig,
    PhaseConfig,
    TotalsConfig,
)


def _ev(value, ts="2024-01-01T00:00:00Z"):
    """Helper: create EntityValue with converted_value == value."""
    return EntityValue(value=value, unit="W", converted_value=value, last_updated=ts)


class TestPhaseData:
    """Tests for the PhaseData dataclass."""

    def test_defaults(self):
        """Test PhaseData default values."""
        phase = PhaseData()

        assert phase.voltage == 230.0
        assert phase.current == 0.0
        assert phase.power == 0.0
        assert phase.power_returned == 0.0
        assert phase.apparent_power == 0.0
        assert phase.power_factor == 1.0
        assert phase.frequency == 50.0
        assert phase.energy_total == 0.0
        assert phase.energy_returned_total == 0.0

    def test_active_power_consumption(self):
        """Test active_power property with consumption."""
        phase = PhaseData(power=1000.0, power_returned=0.0)

        assert phase.active_power == 1000.0

    def test_active_power_production(self):
        """Test active_power property with production."""
        phase = PhaseData(power=0.0, power_returned=500.0)

        assert phase.active_power == -500.0

    def test_active_power_net(self):
        """Test active_power property with both consumption and production."""
        phase = PhaseData(power=1000.0, power_returned=300.0)

        assert phase.active_power == 700.0

    def test_calculate_derived_apparent_power(self):
        """Test calculate_derived for apparent power."""
        phase = PhaseData(voltage=230.0, current=10.0, apparent_power=0.0)

        phase.calculate_derived()

        assert phase.apparent_power == 2300.0  # 230V * 10A

    def test_calculate_derived_apparent_power_negative(self):
        """Test calculate_derived signs apparent power negative during export."""
        phase = PhaseData(voltage=230.0, current=10.0, power_returned=2000.0)

        phase.calculate_derived()

        assert phase.apparent_power == -2300.0  # 230V * 10A, negative for export

    def test_calculate_derived_apparent_power_existing(self):
        """Test calculate_derived doesn't overwrite existing apparent power."""
        phase = PhaseData(voltage=230.0, current=10.0, apparent_power=2000.0)

        phase.calculate_derived()

        assert phase.apparent_power == 2000.0  # Unchanged

    def test_calculate_derived_power_factor(self):
        """Test calculate_derived for power factor."""
        phase = PhaseData(
            power=1800.0,
            power_returned=0.0,
            apparent_power=2000.0,
        )

        phase.calculate_derived()

        assert phase.power_factor == 0.9  # 1800/2000

    def test_calculate_derived_power_factor_negative_apparent(self):
        """Test calculate_derived computes power factor with negative apparent power."""
        phase = PhaseData(
            power=0.0,
            power_returned=1800.0,
            apparent_power=-2000.0,
        )

        phase.calculate_derived()

        assert phase.power_factor == 0.9  # |-1800| / |-2000|

    def test_calculate_derived_power_factor_capped(self):
        """Test calculate_derived caps power factor at 1.0."""
        phase = PhaseData(
            power=2500.0,
            power_returned=0.0,
            apparent_power=2000.0,
        )

        phase.calculate_derived()

        assert phase.power_factor == 1.0  # Capped

    def test_calculate_derived_zero_apparent_power(self):
        """Test calculate_derived with zero apparent power."""
        phase = PhaseData(apparent_power=0.0, power=1000.0)

        phase.calculate_derived()

        # Power factor should remain default when apparent power is zero
        assert phase.power_factor == 1.0


class TestMeterData:
    """Tests for the MeterData dataclass."""

    def test_defaults(self):
        """Test MeterData default values."""
        data = MeterData()

        assert data.total_energy == 0.0
        assert data.total_energy_returned == 0.0
        assert data.timestamp == 0.0
        assert data.is_valid is False

    def test_total_power(self):
        """Test total_power property."""
        data = MeterData(
            phase_a=PhaseData(power=1000.0, power_returned=0.0),
            phase_b=PhaseData(power=800.0, power_returned=0.0),
            phase_c=PhaseData(power=600.0, power_returned=200.0),
        )

        assert data.total_power == 2200.0  # 1000 + 800 + (600-200)

    def test_total_current(self):
        """Test total_current property."""
        data = MeterData(
            phase_a=PhaseData(current=5.0),
            phase_b=PhaseData(current=3.0),
            phase_c=PhaseData(current=4.0),
        )

        assert data.total_current == 12.0

    def test_total_apparent_power(self):
        """Test total_apparent_power property."""
        data = MeterData(
            phase_a=PhaseData(apparent_power=1000.0),
            phase_b=PhaseData(apparent_power=800.0),
            phase_c=PhaseData(apparent_power=600.0),
        )

        assert data.total_apparent_power == 2400.0

    def test_total_apparent_power_with_export(self):
        """Test total_apparent_power with mixed consumption and export."""
        data = MeterData(
            phase_a=PhaseData(apparent_power=-1000.0),
            phase_b=PhaseData(apparent_power=800.0),
            phase_c=PhaseData(apparent_power=-600.0),
        )

        assert data.total_apparent_power == -800.0  # -1000 + 800 + -600


class TestDataManager:
    """Tests for the DataManager class."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        return Settings(
            homeassistant=HomeAssistantConfig(
                url="http://localhost:8123",
                token="test-token",
                poll_interval=0.1,  # Fast polling for tests
            ),
            dsmr=DSMRConfig(
                auto_discover=False,
                single_phase={"power": "sensor.power"},
            ),
        )

    @pytest.fixture
    def mock_settings_three_phase(self):
        """Create mock settings for three-phase."""
        return Settings(
            homeassistant=HomeAssistantConfig(
                url="http://localhost:8123",
                token="test-token",
                poll_interval=0.1,
            ),
            dsmr=DSMRConfig(
                auto_discover=False,
                three_phase={
                    "phase_a": {
                        "voltage": "sensor.voltage_l1",
                        "current": "sensor.current_l1",
                        "power": "sensor.power_l1",
                        "power_returned": "sensor.power_returned_l1",
                    },
                    "phase_b": {
                        "current": "sensor.current_l2",
                        "power": "sensor.power_l2",
                    },
                    "phase_c": {
                        "current": "sensor.current_l3",
                        "power": "sensor.power_l3",
                    },
                },
            ),
        )

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_init(self, mock_ha_client, mock_settings):
        """Test DataManager initialization."""
        manager = DataManager(mock_settings)

        assert manager._settings is mock_settings
        assert manager._poll_thread is None
        mock_ha_client.assert_called_once()

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_get_data_returns_copy(self, mock_ha_client, mock_settings):
        """Test get_data returns a copy of data."""
        manager = DataManager(mock_settings)
        manager._data.phase_a.power = 1000.0

        data = manager.get_data()

        # Modify returned data
        data.phase_a.power = 2000.0

        # Original should be unchanged
        assert manager._data.phase_a.power == 1000.0

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_start_stop(self, mock_ha_client, mock_settings):
        """Test starting and stopping the data manager."""
        mock_client = MagicMock()
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings)

        manager.start()
        assert manager._poll_thread is not None
        assert manager._poll_thread.is_alive()

        manager.stop()
        assert manager._poll_thread is None
        mock_client.close.assert_called_once()

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_start_already_started(self, mock_ha_client, mock_settings):
        """Test start when already started."""
        manager = DataManager(mock_settings)

        manager.start()
        first_thread = manager._poll_thread

        manager.start()  # Should be no-op

        assert manager._poll_thread is first_thread

        manager.stop()

    @patch("src.emulator.data_manager.HomeAssistantClient")
    @patch("src.emulator.data_manager.discover_dsmr_entities")
    def test_start_with_auto_discover(
        self, mock_discover, mock_ha_client, mock_settings
    ):
        """Test start with auto-discovery enabled."""
        mock_settings.dsmr.auto_discover = True

        mock_discovered = MagicMock()
        mock_discovered.has_power_data.return_value = True
        mock_discovered.is_three_phase = False
        mock_discovered.power_total = "sensor.power"
        mock_discovered.power_returned_total = None
        mock_discovered.totals = MagicMock()
        mock_discover.return_value = mock_discovered

        manager = DataManager(mock_settings)
        manager.start()

        mock_discover.assert_called_once()
        manager.stop()

    @patch("src.emulator.data_manager.HomeAssistantClient")
    @patch("src.emulator.data_manager.discover_dsmr_entities")
    def test_start_auto_discover_no_power_data(
        self, mock_discover, mock_ha_client, mock_settings
    ):
        """Test start with auto-discovery when no power data found."""
        mock_settings.dsmr.auto_discover = True

        mock_discovered = MagicMock()
        mock_discovered.has_power_data.return_value = False
        mock_discover.return_value = mock_discovered

        manager = DataManager(mock_settings)
        manager.start()

        # Should still start, just with warning logged
        assert manager._poll_thread is not None
        manager.stop()

    @patch("src.emulator.data_manager.HomeAssistantClient")
    @patch("src.emulator.data_manager.discover_dsmr_entities")
    def test_start_auto_discover_exception(
        self, mock_discover, mock_ha_client, mock_settings
    ):
        """Test start with auto-discovery exception."""
        mock_settings.dsmr.auto_discover = True
        mock_discover.side_effect = Exception("Discovery failed")

        manager = DataManager(mock_settings)
        manager.start()

        # Should still start despite discovery failure
        assert manager._poll_thread is not None
        manager.stop()

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_single_phase_positive(self, mock_ha_client, mock_settings):
        """Test _fetch_data with single phase positive power."""
        mock_client = MagicMock()
        mock_client.get_entity_with_unit.return_value = _ev(1500.0)
        mock_client.get_value.return_value = None
        mock_client.is_connected.return_value = True
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings)
        manager._fetch_data()

        data = manager.get_data()
        assert data.phase_a.power == 1500.0
        assert data.is_valid is True

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_single_phase_negative(self, mock_ha_client, mock_settings):
        """Test _fetch_data with single phase negative power (production)."""
        mock_client = MagicMock()
        mock_client.get_entity_with_unit.return_value = _ev(-500.0)
        mock_client.get_value.return_value = None
        mock_client.is_connected.return_value = True
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings)
        manager._fetch_data()

        data = manager.get_data()
        assert data.phase_a.power == 0.0
        assert data.phase_a.power_returned == 500.0

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_three_phase(self, mock_ha_client, mock_settings_three_phase):
        """Test _fetch_data with three phase configuration."""
        mock_client = MagicMock()

        def get_value_side_effect(entity_id):
            return {
                "sensor.voltage_l1": 231.0,
                "sensor.current_l1": 5.0,
                "sensor.current_l2": 3.0,
                "sensor.current_l3": 4.0,
            }.get(entity_id, None)

        def get_entity_side_effect(entity_id):
            return {
                "sensor.power_l1": _ev(1000.0),
                "sensor.power_returned_l1": _ev(0.0),
                "sensor.power_l2": _ev(600.0),
                "sensor.power_l3": _ev(800.0),
            }.get(entity_id, EntityValue(None, None, None))

        mock_client.get_value.side_effect = get_value_side_effect
        mock_client.get_entity_with_unit.side_effect = get_entity_side_effect
        mock_client.is_connected.return_value = True
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings_three_phase)
        manager._fetch_data()

        data = manager.get_data()
        assert data.phase_a.voltage == 231.0
        assert data.phase_a.current == 5.0
        assert data.phase_a.power == 1000.0
        assert data.phase_b.power == 600.0
        assert data.phase_c.power == 800.0

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_energy_totals(self, mock_ha_client, mock_settings):
        """Test _fetch_data with energy totals."""
        mock_client = MagicMock()
        mock_client.get_entity_with_unit.return_value = _ev(1000.0)

        def get_value_side_effect(entity_id):
            return {
                "sensor.energy_delivered": 10000.0,
                "sensor.energy_returned": 5000.0,
            }.get(entity_id, None)

        mock_client.get_value.side_effect = get_value_side_effect
        mock_client.is_connected.return_value = True
        mock_ha_client.return_value = mock_client

        mock_settings.dsmr.totals = TotalsConfig(
            energy_delivered="sensor.energy_delivered",
            energy_returned="sensor.energy_returned",
        )

        manager = DataManager(mock_settings)
        manager._fetch_data()

        data = manager.get_data()
        assert data.total_energy == 10000.0
        assert data.total_energy_returned == 5000.0

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_tariff_fallback(self, mock_ha_client, mock_settings):
        """Test _fetch_data falls back to tariff-based energy totals."""
        mock_client = MagicMock()
        mock_client.get_entity_with_unit.return_value = _ev(1000.0)

        def get_value_side_effect(entity_id):
            return {
                "sensor.delivered_tariff_1": 6000.0,
                "sensor.delivered_tariff_2": 4000.0,
                "sensor.returned_tariff_1": 3000.0,
                "sensor.returned_tariff_2": 2000.0,
            }.get(entity_id, None)

        mock_client.get_value.side_effect = get_value_side_effect
        mock_client.is_connected.return_value = True
        mock_ha_client.return_value = mock_client

        mock_settings.dsmr.totals = TotalsConfig(
            energy_delivered_tariff_1="sensor.delivered_tariff_1",
            energy_delivered_tariff_2="sensor.delivered_tariff_2",
            energy_returned_tariff_1="sensor.returned_tariff_1",
            energy_returned_tariff_2="sensor.returned_tariff_2",
        )

        manager = DataManager(mock_settings)
        manager._fetch_data()

        data = manager.get_data()
        assert data.total_energy == 10000.0  # 6000 + 4000
        assert data.total_energy_returned == 5000.0  # 3000 + 2000

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_skips_unchanged(self, mock_ha_client, mock_settings):
        """Test _fetch_data skips update when no sensor data has changed."""
        mock_client = MagicMock()
        mock_client.get_value.return_value = None
        mock_client.is_connected.return_value = True
        # First call: new timestamp → changed. Second call: same timestamp → skip.
        mock_client.get_entity_with_unit.side_effect = [
            _ev(1500.0, "2024-01-01T00:00:00Z"),
            _ev(2000.0, "2024-01-01T00:00:00Z"),  # Same timestamp
        ]
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings)

        # First fetch should update
        manager._fetch_data()
        data1 = manager.get_data()
        assert data1.phase_a.power == 1500.0

        # Second fetch should skip because timestamp unchanged
        manager._data.is_valid = True
        manager._fetch_data()
        data2 = manager.get_data()
        assert data2.phase_a.power == 1500.0

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_checks_all_sensors_three_phase(
        self, mock_ha_client, mock_settings_three_phase
    ):
        """Test _fetch_data checks all power sensors via get_entity_with_unit."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_ha_client.return_value = mock_client

        def get_value_side_effect(entity_id):
            return {
                "sensor.voltage_l1": 231.0,
                "sensor.current_l1": 5.0,
                "sensor.current_l2": 3.0,
                "sensor.current_l3": 4.0,
            }.get(entity_id, None)

        def get_entity_side_effect(entity_id):
            return {
                "sensor.power_l1": _ev(1000.0),
                "sensor.power_returned_l1": _ev(0.0),
                "sensor.power_l2": _ev(600.0),
                "sensor.power_l3": _ev(800.0),
            }.get(entity_id, EntityValue(None, None, None))

        mock_client.get_value.side_effect = get_value_side_effect
        mock_client.get_entity_with_unit.side_effect = get_entity_side_effect

        manager = DataManager(mock_settings_three_phase)
        manager._fetch_data()

        # Verify get_entity_with_unit was called for all 4 power entities
        entity_calls = [call[0][0] for call in mock_client.get_entity_with_unit.call_args_list]
        assert "sensor.power_l1" in entity_calls
        assert "sensor.power_returned_l1" in entity_calls
        assert "sensor.power_l2" in entity_calls
        assert "sensor.power_l3" in entity_calls

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_updates_when_one_sensor_changes(
        self, mock_ha_client, mock_settings_three_phase
    ):
        """Test that data is fetched if even one sensor has changed."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_ha_client.return_value = mock_client

        def get_value_side_effect(entity_id):
            return {
                "sensor.voltage_l1": 231.0,
                "sensor.current_l1": 5.0,
                "sensor.current_l2": 3.0,
                "sensor.current_l3": 4.0,
            }.get(entity_id, None)

        # power_l3 has a different timestamp → triggers update
        def get_entity_side_effect(entity_id):
            return {
                "sensor.power_l1": _ev(1000.0, "2024-01-01T00:00:00Z"),
                "sensor.power_returned_l1": _ev(0.0, "2024-01-01T00:00:00Z"),
                "sensor.power_l2": _ev(600.0, "2024-01-01T00:00:00Z"),
                "sensor.power_l3": _ev(800.0, "2024-01-01T00:00:01Z"),  # changed!
            }.get(entity_id, EntityValue(None, None, None))

        mock_client.get_value.side_effect = get_value_side_effect
        mock_client.get_entity_with_unit.side_effect = get_entity_side_effect

        manager = DataManager(mock_settings_three_phase)
        manager._data.is_valid = True

        manager._fetch_data()

        data = manager.get_data()
        assert data.phase_a.power == 1000.0
        assert data.phase_c.power == 800.0
        assert data.is_valid is True

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_data_skips_when_all_sensors_unchanged(
        self, mock_ha_client, mock_settings_three_phase
    ):
        """Test that data fetch is skipped when ALL sensors are unchanged."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings_three_phase)
        manager._data.is_valid = True
        manager._data.phase_a.power = 999.0  # Old value

        # Pre-populate timestamps so all sensors appear "unchanged"
        same_ts = "2024-01-01T00:00:00Z"
        manager._last_timestamps = {
            "sensor.power_l1": same_ts,
            "sensor.power_returned_l1": same_ts,
            "sensor.power_l2": same_ts,
            "sensor.power_l3": same_ts,
        }

        def get_entity_side_effect(entity_id):
            return {
                "sensor.power_l1": _ev(5000.0, same_ts),
                "sensor.power_returned_l1": _ev(0.0, same_ts),
                "sensor.power_l2": _ev(5000.0, same_ts),
                "sensor.power_l3": _ev(5000.0, same_ts),
            }.get(entity_id, EntityValue(None, None, None))

        mock_client.get_entity_with_unit.side_effect = get_entity_side_effect
        mock_client.get_value.return_value = None

        manager._fetch_data()

        # Should still have old value since all sensors unchanged
        data = manager.get_data()
        assert data.phase_a.power == 999.0

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_poll_loop_exception_handling(self, mock_ha_client, mock_settings):
        """Test poll loop handles exceptions gracefully."""
        mock_client = MagicMock()
        mock_client.get_entity_with_unit.side_effect = Exception("API Error")
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings)
        manager.start()

        # Let it run a few iterations
        time.sleep(0.3)

        # Should still be running despite errors
        assert manager._poll_thread.is_alive()

        manager.stop()

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_phase_data(self, mock_ha_client, mock_settings_three_phase):
        """Test _fetch_phase_data method."""
        mock_client = MagicMock()
        mock_client.get_value.side_effect = [231.0, 5.5]  # voltage, current
        mock_client.get_entity_with_unit.side_effect = [
            _ev(1100.0),  # power
            _ev(50.0),    # power_returned
        ]
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings_three_phase)

        phase_config = PhaseConfig(
            voltage="sensor.voltage",
            current="sensor.current",
            power="sensor.power",
            power_returned="sensor.power_returned",
        )
        phase_data = PhaseData()

        changed = manager._fetch_phase_data(phase_config, phase_data)

        assert phase_data.voltage == 231.0
        assert phase_data.current == 5.5
        assert phase_data.power == 1100.0
        assert phase_data.power_returned == 50.0
        assert changed is True  # new timestamps detected

    @patch("src.emulator.data_manager.HomeAssistantClient")
    def test_fetch_phase_data_none_values(
        self, mock_ha_client, mock_settings_three_phase
    ):
        """Test _fetch_phase_data handles None values."""
        mock_client = MagicMock()
        mock_client.get_value.return_value = None
        mock_client.get_entity_with_unit.return_value = EntityValue(None, None, None)
        mock_ha_client.return_value = mock_client

        manager = DataManager(mock_settings_three_phase)

        phase_config = PhaseConfig(
            voltage="sensor.voltage",
            current="sensor.current",
        )
        phase_data = PhaseData()

        changed = manager._fetch_phase_data(phase_config, phase_data)

        # Should keep defaults
        assert phase_data.voltage == 230.0
        assert phase_data.current == 0.0
        assert changed is False
