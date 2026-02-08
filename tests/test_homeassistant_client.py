"""Tests for the Home Assistant client module."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.data_sources.homeassistant import (
    HomeAssistantClient,
    EntityValue,
    UNIT_CONVERSIONS,
)


class TestUnitConversions:
    """Tests for unit conversion constants."""

    def test_kw_to_w(self):
        """Test kW to W conversion factor."""
        assert UNIT_CONVERSIONS["kW"] == 1000.0

    def test_mw_to_w(self):
        """Test MW to W conversion factor."""
        assert UNIT_CONVERSIONS["MW"] == 1000000.0

    def test_kwh_to_wh(self):
        """Test kWh to Wh conversion factor."""
        assert UNIT_CONVERSIONS["kWh"] == 1000.0

    def test_mwh_to_wh(self):
        """Test MWh to Wh conversion factor."""
        assert UNIT_CONVERSIONS["MWh"] == 1000000.0


class TestEntityValue:
    """Tests for the EntityValue dataclass."""

    def test_entity_value_with_values(self):
        """Test EntityValue with all values set."""
        ev = EntityValue(value=1.5, unit="kW", converted_value=1500.0)

        assert ev.value == 1.5
        assert ev.unit == "kW"
        assert ev.converted_value == 1500.0

    def test_entity_value_none_values(self):
        """Test EntityValue with None values."""
        ev = EntityValue(value=None, unit=None, converted_value=None)

        assert ev.value is None
        assert ev.unit is None
        assert ev.converted_value is None


class TestHomeAssistantClient:
    """Tests for the HomeAssistantClient class."""

    @pytest.fixture
    def client(self):
        """Create a HomeAssistantClient for testing."""
        with patch("httpx.Client"):
            client = HomeAssistantClient(
                url="http://192.168.1.100:8123",
                token="test-token",
                use_https=False,
                verify_ssl=True,
                timeout=10.0,
            )
            yield client
            client.close()

    def test_init(self):
        """Test client initialization."""
        with patch("httpx.Client") as mock_client_class:
            client = HomeAssistantClient(
                url="http://192.168.1.100:8123/",  # With trailing slash
                token="my-token",
                timeout=15.0,
            )

            assert client._base_url == "http://192.168.1.100:8123"  # Stripped
            assert client._token == "my-token"
            assert client._timeout == 15.0
            assert client._connected is False

            # Check httpx.Client was created with correct headers
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args[1]
            assert "Bearer my-token" in call_kwargs["headers"]["Authorization"]

    def test_init_with_https_upgrade(self):
        """Test client initialization with HTTPS upgrade."""
        with patch("httpx.Client"):
            client = HomeAssistantClient(
                url="http://192.168.1.100:8123",
                token="test",
                use_https=True,
            )

            assert client._base_url == "https://192.168.1.100:8123"

    def test_init_already_https(self):
        """Test client initialization with existing HTTPS."""
        with patch("httpx.Client"):
            client = HomeAssistantClient(
                url="https://192.168.1.100:8123",
                token="test",
                use_https=True,
            )

            # Should not double-replace
            assert client._base_url == "https://192.168.1.100:8123"

    def test_get_value_success(self, client):
        """Test successful value retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "state": "1500.5",
            "attributes": {"unit_of_measurement": "W"},
        }
        client._client.get.return_value = mock_response

        value = client.get_value("sensor.power")

        assert value == 1500.5
        assert client._connected is True
        assert client._last_error is None

    def test_get_value_with_kw_conversion(self, client):
        """Test value retrieval with kW to W conversion."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "state": "1.5",
            "attributes": {"unit_of_measurement": "kW"},
        }
        client._client.get.return_value = mock_response

        value = client.get_value("sensor.power")

        assert value == 1500.0  # 1.5 kW * 1000

    def test_get_value_with_kwh_conversion(self, client):
        """Test value retrieval with kWh to Wh conversion."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "state": "25.5",
            "attributes": {"unit_of_measurement": "kWh"},
        }
        client._client.get.return_value = mock_response

        value = client.get_value("sensor.energy")

        assert value == 25500.0  # 25.5 kWh * 1000

    def test_get_value_no_conversion(self, client):
        """Test value retrieval without auto-conversion."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "state": "1.5",
            "attributes": {"unit_of_measurement": "kW"},
        }
        client._client.get.return_value = mock_response

        value = client.get_value("sensor.power", auto_convert=False)

        assert value == 1.5  # No conversion

    def test_get_value_empty_entity_id(self, client):
        """Test get_value with empty entity ID."""
        assert client.get_value("") is None
        assert client.get_value(None) is None

    def test_get_value_unavailable(self, client):
        """Test get_value when entity is unavailable."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "unavailable"}
        client._client.get.return_value = mock_response

        value = client.get_value("sensor.power")

        assert value is None

    def test_get_value_unknown(self, client):
        """Test get_value when entity state is unknown."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "unknown"}
        client._client.get.return_value = mock_response

        value = client.get_value("sensor.power")

        assert value is None

    def test_get_value_http_error(self, client):
        """Test get_value with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        client._client.get.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )

        value = client.get_value("sensor.nonexistent")

        assert value is None
        assert "HTTP error" in client._last_error

    def test_get_value_request_error(self, client):
        """Test get_value with request error."""
        client._client.get.side_effect = httpx.RequestError("Connection failed")

        value = client.get_value("sensor.power")

        assert value is None
        assert client._connected is False
        assert "Request error" in client._last_error

    def test_get_value_parse_error(self, client):
        """Test get_value with value parse error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "not_a_number"}
        client._client.get.return_value = mock_response

        value = client.get_value("sensor.power")

        assert value is None
        assert "Value error" in client._last_error

    def test_get_entity_with_unit_success(self, client):
        """Test get_entity_with_unit success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "state": "1.5",
            "attributes": {"unit_of_measurement": "kW"},
        }
        client._client.get.return_value = mock_response

        result = client.get_entity_with_unit("sensor.power")

        assert result.value == 1.5
        assert result.unit == "kW"
        assert result.converted_value == 1500.0

    def test_get_entity_with_unit_empty_id(self, client):
        """Test get_entity_with_unit with empty ID."""
        result = client.get_entity_with_unit("")

        assert result.value is None
        assert result.unit is None
        assert result.converted_value is None

    def test_get_entity_with_unit_unavailable(self, client):
        """Test get_entity_with_unit when unavailable."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"state": "unavailable"}
        client._client.get.return_value = mock_response

        result = client.get_entity_with_unit("sensor.power")

        assert result.value is None

    def test_get_entity_with_unit_no_unit(self, client):
        """Test get_entity_with_unit when no unit defined."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "state": "42.0",
            "attributes": {},
        }
        client._client.get.return_value = mock_response

        result = client.get_entity_with_unit("sensor.count")

        assert result.value == 42.0
        assert result.unit is None
        assert result.converted_value == 42.0  # No conversion

    def test_get_entity_with_unit_exception(self, client):
        """Test get_entity_with_unit handles exceptions."""
        client._client.get.side_effect = Exception("Error")

        result = client.get_entity_with_unit("sensor.power")

        assert result.value is None

    def test_is_connected(self, client):
        """Test is_connected property."""
        assert client.is_connected() is False

        client._connected = True
        assert client.is_connected() is True

    def test_test_connection_success(self, client):
        """Test test_connection success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": "API running."}
        client._client.get.return_value = mock_response

        result = client.test_connection()

        assert result is True
        assert client._connected is True

    def test_test_connection_no_message(self, client):
        """Test test_connection with unexpected response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # No message
        client._client.get.return_value = mock_response

        result = client.test_connection()

        assert result is False

    def test_test_connection_error(self, client):
        """Test test_connection with error."""
        client._client.get.side_effect = Exception("Connection failed")

        result = client.test_connection()

        assert result is False
        assert client._connected is False

    def test_close(self, client):
        """Test close method."""
        client.close()

        client._client.close.assert_called_once()

    def test_last_error_property(self, client):
        """Test last_error property."""
        assert client.last_error is None

        client._last_error = "Test error"
        assert client.last_error == "Test error"
