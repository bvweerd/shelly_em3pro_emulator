"""Tests for the UDP server module."""

import json
import socket
from unittest.mock import MagicMock, patch

import pytest

from src.servers.udp_server import UDPServer


class TestUDPServer:
    """Tests for the UDPServer class."""

    @pytest.fixture
    def mock_data_manager(self, sample_meter_data):
        """Create a mock data manager."""
        manager = MagicMock()
        manager.get_data.return_value = sample_meter_data
        return manager

    @pytest.fixture
    def udp_server(self, shelly_device, mock_data_manager):
        """Create a UDPServer for testing."""
        return UDPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="127.0.0.1",
            ports=[15100, 15200],
        )

    def test_init(self, shelly_device, mock_data_manager):
        """Test UDPServer initialization."""
        server = UDPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="192.168.1.100",
            ports=[1010, 2220],
        )

        assert server._host == "192.168.1.100"
        assert server._ports == [1010, 2220]
        assert server._running is False

    def test_init_default_ports(self, shelly_device, mock_data_manager):
        """Test UDPServer initialization with default ports."""
        server = UDPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
        )

        assert server._ports == [1010, 2220]

    @patch("src.servers.udp_server.socket.socket")
    def test_start_stop(self, mock_socket_class, udp_server):
        """Test starting and stopping the UDP server."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        udp_server.start()

        assert udp_server._running is True
        assert len(udp_server._sockets) == 2
        assert len(udp_server._threads) == 2

        udp_server.stop()

        assert udp_server._running is False
        assert len(udp_server._sockets) == 0
        assert len(udp_server._threads) == 0

    @patch("src.servers.udp_server.socket.socket")
    def test_start_already_running(self, mock_socket_class, udp_server):
        """Test starting when already running."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        udp_server.start()

        # Start again should be no-op
        udp_server.start()

        assert len(udp_server._sockets) == 2  # Still only 2

        udp_server.stop()

    def test_stop_not_running(self, udp_server):
        """Test stopping when not running."""
        # Should not raise
        udp_server.stop()

    @patch("src.servers.udp_server.socket.socket")
    def test_start_bind_failure(
        self, mock_socket_class, shelly_device, mock_data_manager
    ):
        """Test start with bind failure."""
        mock_socket = MagicMock()
        mock_socket.bind.side_effect = OSError("Address already in use")
        mock_socket_class.return_value = mock_socket

        server = UDPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="127.0.0.1",
            ports=[1010],
        )

        # Should not raise, just log error
        server.start()
        server.stop()

    def test_format_power_zero(self):
        """Test _format_power with zero."""
        result = UDPServer._format_power(0.0)
        assert result == 0.001

    def test_format_power_small(self):
        """Test _format_power with small value."""
        result = UDPServer._format_power(0.05)
        assert result == 0.001

    def test_format_power_whole_number(self):
        """Test _format_power with whole number."""
        result = UDPServer._format_power(100.0)
        # Should add decimal enforcer
        assert result == 100.001

    def test_format_power_with_decimal(self):
        """Test _format_power with decimal value."""
        result = UDPServer._format_power(100.5)
        # Should keep decimal
        assert result == 100.5

    def test_format_power_negative(self):
        """Test _format_power with negative value."""
        result = UDPServer._format_power(-500.0)
        assert result == -500.001  # -500 - 0.001 (enforcer in direction of sign)

    def test_format_power_small_negative(self):
        """Test _format_power with small negative value preserves sign."""
        result = UDPServer._format_power(-0.05)
        assert result == -0.001  # Preserves negative sign

    def test_create_em_response(self, udp_server):
        """Test _create_em_response."""
        response = udp_server._create_em_response(123)

        assert response["id"] == 123
        assert "result" in response
        assert "a_act_power" in response["result"]
        assert "total_act_power" in response["result"]

    def test_create_em1_response(self, udp_server):
        """Test _create_em1_response."""
        response = udp_server._create_em1_response(456)

        assert response["id"] == 456
        assert "result" in response
        assert "act_power" in response["result"]

    def test_create_device_info_response(self, udp_server):
        """Test _create_device_info_response."""
        response = udp_server._create_device_info_response(789)

        assert response["id"] == 789
        assert "result" in response

    def test_process_request_em_get_status(self, udp_server):
        """Test _process_request for EM.GetStatus."""
        request = {"method": "EM.GetStatus", "id": 1, "params": {"id": 0}}
        response = udp_server._process_request(request)

        assert response is not None
        assert response["id"] == 1

    def test_process_request_em1_get_status(self, udp_server):
        """Test _process_request for EM1.GetStatus."""
        request = {"method": "EM1.GetStatus", "id": 2, "params": {"id": 0}}
        response = udp_server._process_request(request)

        assert response is not None
        assert response["id"] == 2

    def test_process_request_device_info(self, udp_server):
        """Test _process_request for Shelly.GetDeviceInfo."""
        request = {"method": "Shelly.GetDeviceInfo", "id": 3, "params": {"id": 0}}
        response = udp_server._process_request(request)

        assert response is not None
        assert response["id"] == 3

    def test_process_request_unknown_method(self, udp_server):
        """Test _process_request for unknown method."""
        request = {"method": "Unknown.Method", "id": 4, "params": {"id": 0}}
        response = udp_server._process_request(request)

        assert response is None

    def test_process_request_invalid_params(self, udp_server):
        """Test _process_request with invalid params."""
        request = {"method": "EM.GetStatus", "id": 5, "params": {"id": "invalid"}}
        response = udp_server._process_request(request)

        assert response is None

    def test_process_request_no_params(self, udp_server):
        """Test _process_request with no params."""
        request = {"method": "EM.GetStatus", "id": 6}
        response = udp_server._process_request(request)

        assert response is None

    def test_handle_request_valid(self, udp_server):
        """Test _handle_request with valid request."""
        sock = MagicMock()
        request = {"method": "EM.GetStatus", "id": 1, "params": {"id": 0}}
        data = json.dumps(request).encode("utf-8")
        addr = ("127.0.0.1", 12345)

        udp_server._handle_request(sock, data, addr, 15100)

        sock.sendto.assert_called_once()

    def test_handle_request_invalid_json(self, udp_server):
        """Test _handle_request with invalid JSON."""
        sock = MagicMock()
        data = b"not valid json"
        addr = ("127.0.0.1", 12345)

        # Should not raise
        udp_server._handle_request(sock, data, addr, 15100)

        sock.sendto.assert_not_called()

    def test_handle_request_no_response(self, udp_server):
        """Test _handle_request when no response is needed."""
        sock = MagicMock()
        request = {"method": "Unknown.Method", "id": 1, "params": {"id": 0}}
        data = json.dumps(request).encode("utf-8")
        addr = ("127.0.0.1", 12345)

        udp_server._handle_request(sock, data, addr, 15100)

        sock.sendto.assert_not_called()


class TestUDPServerListenLoop:
    """Tests for UDP server listen loop."""

    @pytest.fixture
    def mock_data_manager(self, sample_meter_data):
        """Create a mock data manager."""
        manager = MagicMock()
        manager.get_data.return_value = sample_meter_data
        return manager

    def test_listen_loop_timeout(self, shelly_device, mock_data_manager):
        """Test listen loop handles timeout correctly."""
        server = UDPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="127.0.0.1",
            ports=[15998],
        )

        mock_socket = MagicMock()
        mock_socket.recvfrom.side_effect = socket.timeout()

        server._running = True

        # Run one iteration then stop
        def stop_after_iteration(*args):
            server._running = False
            raise socket.timeout()

        mock_socket.recvfrom.side_effect = stop_after_iteration

        # Should complete without error
        server._listen_loop(mock_socket, 15998)

    def test_listen_loop_os_error(self, shelly_device, mock_data_manager):
        """Test listen loop handles OS error."""
        server = UDPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="127.0.0.1",
            ports=[15997],
        )

        mock_socket = MagicMock()
        mock_socket.recvfrom.side_effect = OSError("Socket error")

        server._running = True

        # Should complete without error
        server._listen_loop(mock_socket, 15997)

    def test_listen_loop_processes_data(self, shelly_device, mock_data_manager):
        """Test listen loop processes incoming data."""
        server = UDPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="127.0.0.1",
            ports=[15996],
        )

        mock_socket = MagicMock()
        request = {"method": "EM.GetStatus", "id": 1, "params": {"id": 0}}

        call_count = [0]

        def recvfrom_side_effect(size):
            call_count[0] += 1
            if call_count[0] == 1:
                return (json.dumps(request).encode(), ("127.0.0.1", 12345))
            else:
                server._running = False
                raise socket.timeout()

        mock_socket.recvfrom.side_effect = recvfrom_side_effect

        # Mock executor to avoid threading issues
        with patch.object(server, "_executor") as mock_executor:
            server._running = True
            server._listen_loop(mock_socket, 15996)

            # Executor submit should have been called
            mock_executor.submit.assert_called_once()
