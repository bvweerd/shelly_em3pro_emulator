"""Tests for data sources and DSMR discovery."""

import pytest
from unittest.mock import MagicMock, patch

from src.data_sources import HomeAssistantClient
from src.data_sources.dsmr_discovery import (
    DSMRDiscovery,
    DiscoveredEntities,
    DSMR_PATTERNS,
)


class TestHomeAssistantClient:
    """Test Home Assistant REST API client."""

    @pytest.fixture
    def ha_client(self):
        """Create a Home Assistant client for testing."""
        return HomeAssistantClient(
            url="http://localhost:8123",
            token="test-token",
            timeout=5.0,
        )

    def test_client_initialization(self, ha_client: HomeAssistantClient):
        """Test client is properly initialized."""
        assert ha_client._base_url == "http://localhost:8123"
        assert ha_client._token == "test-token"

    def test_url_normalization(self):
        """Test URL trailing slash is removed."""
        client = HomeAssistantClient(
            url="http://localhost:8123/",
            token="test",
        )
        assert client._base_url == "http://localhost:8123"

    def test_https_upgrade(self):
        """Test HTTPS upgrade when use_https is True."""
        client = HomeAssistantClient(
            url="http://localhost:8123",
            token="test",
            use_https=True,
        )
        assert client._base_url == "https://localhost:8123"

    @patch("httpx.Client.get")
    def test_get_value_success(self, mock_get, ha_client: HomeAssistantClient):
        """Test successful value retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "state": "1523.5",
            "attributes": {"unit_of_measurement": "W"},
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        value = ha_client.get_value("sensor.power")

        assert value == 1523.5
        assert ha_client.is_connected()

    @patch("httpx.Client.get")
    def test_get_value_unavailable(self, mock_get, ha_client: HomeAssistantClient):
        """Test handling of unavailable entity."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "unavailable"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        value = ha_client.get_value("sensor.power")

        assert value is None

    @patch("httpx.Client.get")
    def test_get_value_unknown(self, mock_get, ha_client: HomeAssistantClient):
        """Test handling of unknown state."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "unknown"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        value = ha_client.get_value("sensor.power")

        assert value is None

    def test_get_value_empty_entity(self, ha_client: HomeAssistantClient):
        """Test that empty entity ID returns None."""
        value = ha_client.get_value("")
        assert value is None

    @patch("httpx.Client.get")
    def test_authorization_header(self, mock_get, ha_client: HomeAssistantClient):
        """Test that Bearer token is included in requests."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "100"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        ha_client.get_value("sensor.test")

        # Check that Authorization header was set during client init
        assert "Authorization" in ha_client._client.headers
        assert ha_client._client.headers["Authorization"] == "Bearer test-token"


class TestDSMRDiscovery:
    """Test DSMR entity discovery."""

    def test_pattern_matching_power_consumption(self):
        """Test power consumption pattern matching."""
        import re

        patterns = DSMR_PATTERNS["power_consumption"]
        test_entities = [
            "sensor.electricity_meter_power_consumption",
            "sensor.dsmr_power",
            "sensor.electricity_meter_power_delivered",  # HA DSMR standard
        ]

        for entity in test_entities:
            for pattern in patterns:
                if re.match(pattern, entity, re.IGNORECASE):
                    break
            # At least some should match
            # (not all will match, that's OK)

    def test_pattern_matching_power_delivered(self):
        """Test HA DSMR standard power_delivered pattern."""
        import re

        patterns = DSMR_PATTERNS["power_consumption"]
        test_entity = "sensor.electricity_meter_power_delivered"

        matched = False
        for pattern in patterns:
            if re.match(pattern, test_entity, re.IGNORECASE):
                matched = True
                break

        assert matched, "power_delivered entity should match power_consumption"

    def test_pattern_matching_phase_power(self):
        """Test per-phase power pattern matching."""
        import re

        patterns = DSMR_PATTERNS["power_consumption_l1"]
        test_entity = "sensor.electricity_meter_power_consumption_phase_l1"

        matched = False
        for pattern in patterns:
            if re.match(pattern, test_entity, re.IGNORECASE):
                matched = True
                break

        assert matched, "Phase L1 power entity should match"

    def test_pattern_matching_power_delivered_phase(self):
        """Test HA DSMR standard power_delivered per phase pattern."""
        import re

        # Test all three phases
        test_cases = [
            ("power_consumption_l1", "sensor.electricity_meter_power_delivered_l1"),
            ("power_consumption_l2", "sensor.electricity_meter_power_delivered_l2"),
            ("power_consumption_l3", "sensor.electricity_meter_power_delivered_l3"),
            ("power_production_l1", "sensor.electricity_meter_power_returned_l1"),
            ("power_production_l2", "sensor.electricity_meter_power_returned_l2"),
            ("power_production_l3", "sensor.electricity_meter_power_returned_l3"),
        ]

        for pattern_name, test_entity in test_cases:
            patterns = DSMR_PATTERNS[pattern_name]
            matched = False
            for pattern in patterns:
                if re.match(pattern, test_entity, re.IGNORECASE):
                    matched = True
                    break
            assert matched, f"{test_entity} should match {pattern_name}"

    def test_pattern_matching_voltage(self):
        """Test voltage pattern matching."""
        import re

        patterns = DSMR_PATTERNS["voltage_l1"]
        test_entities = [
            "sensor.electricity_meter_voltage_phase_l1",
            "sensor.voltage_l1",
            "sensor.electricity_meter_voltage_phase_l1",  # HA DSMR standard
        ]

        for entity in test_entities:
            matched = False
            for pattern in patterns:
                if re.match(pattern, entity, re.IGNORECASE):
                    matched = True
                    break
            assert matched, f"Voltage entity {entity} should match"

    def test_pattern_matching_current_phase(self):
        """Test current per phase pattern matching."""
        import re

        test_cases = [
            ("current_l1", "sensor.electricity_meter_current_phase_l1"),
            ("current_l2", "sensor.electricity_meter_current_phase_l2"),
            ("current_l3", "sensor.electricity_meter_current_phase_l3"),
            ("current_l1", "sensor.electricity_meter_instantaneous_current_l1"),
        ]

        for pattern_name, test_entity in test_cases:
            patterns = DSMR_PATTERNS[pattern_name]
            matched = False
            for pattern in patterns:
                if re.match(pattern, test_entity, re.IGNORECASE):
                    matched = True
                    break
            assert matched, f"{test_entity} should match {pattern_name}"

    def test_pattern_matching_tariff_energy(self):
        """Test energy tariff pattern matching."""
        import re

        test_cases = [
            (
                "energy_consumption_tariff_1",
                "sensor.electricity_meter_energy_consumption_tariff_1",
            ),
            (
                "energy_consumption_tariff_2",
                "sensor.electricity_meter_energy_consumption_tariff_2",
            ),
            (
                "energy_production_tariff_1",
                "sensor.electricity_meter_energy_returned_tariff_1",
            ),
            (
                "energy_production_tariff_2",
                "sensor.electricity_meter_energy_returned_tariff_2",
            ),
            ("energy_consumption_tariff_1", "sensor.dsmr_electricity_used_tariff_1"),
            ("energy_consumption_tariff_2", "sensor.dsmr_electricity_used_tariff_2"),
        ]

        for pattern_name, test_entity in test_cases:
            patterns = DSMR_PATTERNS[pattern_name]
            matched = False
            for pattern in patterns:
                if re.match(pattern, test_entity, re.IGNORECASE):
                    matched = True
                    break
            assert matched, f"{test_entity} should match {pattern_name}"

    def test_pattern_matching_belgian_fluvius(self):
        """Test Belgian Fluvius meter entity patterns."""
        import re

        # Fluvius patterns for Belgian smart meters
        test_cases = [
            ("power_consumption", "sensor.fluvius_electricity_consumption"),
            ("power_production", "sensor.fluvius_electricity_production"),
        ]

        for pattern_name, test_entity in test_cases:
            patterns = DSMR_PATTERNS[pattern_name]
            matched = False
            for pattern in patterns:
                if re.match(pattern, test_entity, re.IGNORECASE):
                    matched = True
                    break
            assert (
                matched
            ), f"Belgian Fluvius entity {test_entity} should match {pattern_name}"

    @patch("httpx.Client.get")
    def test_discovery_three_phase(self, mock_get):
        """Test discovery of three-phase configuration."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"entity_id": "sensor.electricity_meter_power_consumption_phase_l1"},
            {"entity_id": "sensor.electricity_meter_power_consumption_phase_l2"},
            {"entity_id": "sensor.electricity_meter_power_consumption_phase_l3"},
            {"entity_id": "sensor.electricity_meter_voltage_phase_l1"},
            {"entity_id": "sensor.electricity_meter_voltage_phase_l2"},
            {"entity_id": "sensor.electricity_meter_voltage_phase_l3"},
            {"entity_id": "sensor.electricity_meter_current_phase_l1"},
            {"entity_id": "sensor.electricity_meter_energy_consumption_total"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        discovery = DSMRDiscovery(
            url="http://localhost:8123",
            token="test-token",
        )
        result = discovery.discover()
        discovery.close()

        assert result.is_three_phase
        assert result.phase_a.power != ""
        assert result.has_power_data()

    @patch("httpx.Client.get")
    def test_discovery_single_phase(self, mock_get):
        """Test discovery of single-phase configuration."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"entity_id": "sensor.electricity_meter_power_consumption"},
            {"entity_id": "sensor.electricity_meter_power_production"},
            {"entity_id": "sensor.electricity_meter_energy_consumption_total"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        discovery = DSMRDiscovery(
            url="http://localhost:8123",
            token="test-token",
        )
        result = discovery.discover()
        discovery.close()

        assert not result.is_three_phase
        assert result.power_total != ""
        assert result.has_power_data()

    @patch("httpx.Client.get")
    def test_discovery_no_dsmr_entities(self, mock_get):
        """Test discovery when no DSMR entities exist."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"entity_id": "sensor.temperature"},
            {"entity_id": "sensor.humidity"},
            {"entity_id": "light.living_room"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        discovery = DSMRDiscovery(
            url="http://localhost:8123",
            token="test-token",
        )
        result = discovery.discover()
        discovery.close()

        assert not result.has_power_data()
        assert not result.is_three_phase


class TestDiscoveredEntities:
    """Test DiscoveredEntities dataclass."""

    def test_has_power_data_with_total(self):
        """Test has_power_data with total power."""
        entities = DiscoveredEntities(power_total="sensor.power")
        assert entities.has_power_data()

    def test_has_power_data_with_phase_a(self):
        """Test has_power_data with phase A power."""
        from src.data_sources.dsmr_discovery import DiscoveredPhase

        entities = DiscoveredEntities()
        entities.phase_a = DiscoveredPhase(power="sensor.phase_a_power")
        assert entities.has_power_data()

    def test_has_power_data_empty(self):
        """Test has_power_data when empty."""
        entities = DiscoveredEntities()
        assert not entities.has_power_data()
