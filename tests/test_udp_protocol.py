"""Tests for UDP JSON-RPC protocol."""

import json
import time
from unittest.mock import MagicMock

import pytest

from src.emulator import DataManager, MeterData, PhaseData, ShellyDevice
from src.servers import UDPServer


class TestUDPProtocol:
    """Test UDP JSON-RPC protocol implementation.

    These tests use mocked socket operations and test the protocol
    handling directly through the server's internal methods.
    """

    @pytest.fixture
    def udp_server(
        self,
        shelly_device: ShellyDevice,
        mock_data_manager,
    ):
        """Create a UDP server instance (without starting network listener)."""
        server = UDPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="127.0.0.1",
            ports=[15010],
        )
        # Don't call start() - we'll test the protocol directly
        yield server

    def test_em_get_status_response_format(
        self,
        udp_server: UDPServer,
    ):
        """Test EM.GetStatus returns correct response format."""
        request = {
            "id": 42,
            "method": "EM.GetStatus",
            "params": {"id": 0},
        }
        response = udp_server._process_request(request)

        assert response["id"] == 42
        assert "src" in response
        assert "result" in response
        # Check error fields are present
        result = response["result"]
        assert "a_errors" in result
        assert "b_errors" in result
        assert "c_errors" in result
        assert "n_errors" in result
        assert "errors" in result
        assert isinstance(result["errors"], list)

        result = response["result"]
        assert "a_act_power" in result
        assert "b_act_power" in result
        assert "c_act_power" in result
        assert "total_act_power" in result

    def test_em_get_status_power_values(
        self,
        udp_server: UDPServer,
        sample_meter_data: MeterData,
    ):
        """Test EM.GetStatus returns correct power values."""
        request = {
            "id": 1,
            "method": "EM.GetStatus",
            "params": {"id": 0},
        }
        response = udp_server._process_request(request)
        result = response["result"]

        # Check that power values are numeric
        assert isinstance(result["a_act_power"], (int, float))
        assert isinstance(result["b_act_power"], (int, float))
        assert isinstance(result["c_act_power"], (int, float))
        assert isinstance(result["total_act_power"], (int, float))

        # Values should approximately match our sample data
        # (with some tolerance for decimal enforcement)
        assert abs(result["a_act_power"] - 1150.0) < 2.0
        assert abs(result["b_act_power"] - 850.0) < 2.0
        assert abs(result["c_act_power"] - 1000.0) < 2.0

    def test_em_get_status_voltage_current(
        self,
        udp_server: UDPServer,
    ):
        """Test EM.GetStatus includes voltage and current."""
        request = {
            "id": 1,
            "method": "EM.GetStatus",
            "params": {"id": 0},
        }
        response = udp_server._process_request(request)
        result = response["result"]

        # Check voltage fields
        assert "a_voltage" in result
        assert "b_voltage" in result
        assert "c_voltage" in result

        # Check current fields
        assert "a_current" in result
        assert "b_current" in result
        assert "c_current" in result

        # Voltage should be around 230V
        assert 200 <= result["a_voltage"] <= 260
        assert 200 <= result["b_voltage"] <= 260
        assert 200 <= result["c_voltage"] <= 260

    def test_em1_get_status_response(
        self,
        udp_server: UDPServer,
    ):
        """Test EM1.GetStatus returns correct format."""
        request = {
            "id": 99,
            "method": "EM1.GetStatus",
            "params": {"id": 0},
        }
        response = udp_server._process_request(request)

        assert response["id"] == 99
        assert "result" in response
        assert "act_power" in response["result"]

        # Total power should match sum of phases
        total = response["result"]["act_power"]
        assert abs(total - 3000.0) < 5.0  # 1150 + 850 + 1000

    def test_em_get_ct_types_response(
        self,
        udp_server: UDPServer,
    ):
        """Test EM.GetCTTypes returns supported CT types."""
        request = {
            "id": 50,
            "method": "EM.GetCTTypes",
            "params": {"id": 0},
        }
        response = udp_server._process_request(request)

        assert response["id"] == 50
        result = response["result"]
        assert "types" in result
        assert "120A" in result["types"]
        assert "50A" in result["types"]

    def test_invalid_json_handled(
        self,
        udp_server: UDPServer,
    ):
        """Test that invalid JSON is gracefully handled."""
        # Create a mock socket
        mock_sock = MagicMock()

        # Call _handle_request with invalid JSON
        udp_server._handle_request(
            mock_sock, b"not valid json", ("127.0.0.1", 12345), 15010
        )

        # Should not have sent any response (invalid JSON is ignored)
        mock_sock.sendto.assert_not_called()

    def test_unknown_method_no_response(
        self,
        udp_server: UDPServer,
    ):
        """Test that unknown methods don't get a response."""
        request = {
            "id": 1,
            "method": "Unknown.Method",
            "params": {"id": 0},
        }
        response = udp_server._process_request(request)

        # Unknown methods should return None (no response)
        assert response is None

    def test_request_without_params_id(
        self,
        udp_server: UDPServer,
    ):
        """Test that requests without params.id are ignored."""
        request = {
            "id": 1,
            "method": "EM.GetStatus",
            "params": {},  # No id field
        }
        response = udp_server._process_request(request)

        # Requests without params.id should return None
        assert response is None

    def test_handle_request_sends_response(
        self,
        udp_server: UDPServer,
    ):
        """Test that valid requests get responses sent back."""
        mock_sock = MagicMock()

        request = json.dumps(
            {
                "id": 1,
                "method": "EM.GetStatus",
                "params": {"id": 0},
            }
        ).encode()

        udp_server._handle_request(mock_sock, request, ("127.0.0.1", 12345), 15010)

        # Should have sent a response
        mock_sock.sendto.assert_called_once()
        sent_data, addr = mock_sock.sendto.call_args[0]
        response = json.loads(sent_data.decode())
        assert response["id"] == 1
        assert "result" in response


class TestPowerValueFormatting:
    """Test power value formatting for Marstek compatibility."""

    @pytest.fixture
    def server_with_whole_number_data(
        self,
        shelly_device: ShellyDevice,
    ):
        """Create server with specific test data (whole numbers)."""
        # Create data with whole number power values
        data = MeterData(
            phase_a=PhaseData(power=100.0, power_returned=0.0),
            phase_b=PhaseData(power=200.0, power_returned=0.0),
            phase_c=PhaseData(power=0.0, power_returned=0.0),
            timestamp=time.time(),
            is_valid=True,
        )

        mock_dm = MagicMock(spec=DataManager)
        mock_dm.get_data.return_value = data

        server = UDPServer(
            device=shelly_device,
            data_manager=mock_dm,
            host="127.0.0.1",
            ports=[15011],
        )
        # Don't start the server - test directly
        yield server

    def test_power_values_have_decimals(self, server_with_whole_number_data):
        """Test that power values always have decimal points."""
        request = {
            "id": 1,
            "method": "EM.GetStatus",
            "params": {"id": 0},
        }
        response = server_with_whole_number_data._process_request(request)
        result = response["result"]

        # Whole numbers should have .001 added
        a_power = result["a_act_power"]
        assert "." in str(a_power) or a_power != int(a_power)

    def test_zero_power_formatted(self, server_with_whole_number_data):
        """Test that zero power is formatted correctly."""
        request = {
            "id": 1,
            "method": "EM.GetStatus",
            "params": {"id": 0},
        }
        response = server_with_whole_number_data._process_request(request)
        result = response["result"]

        # Zero should become 0.001
        c_power = result["c_act_power"]
        assert c_power == 0.001
