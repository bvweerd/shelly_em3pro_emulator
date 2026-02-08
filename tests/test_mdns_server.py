"""Tests for the mDNS server module."""

from unittest.mock import MagicMock, patch


from src.servers.mdns_server import MDNSServer


class TestMDNSServer:
    """Tests for the MDNSServer class."""

    def test_init(self):
        """Test MDNSServer initialization."""
        server = MDNSServer(
            device_name="Test Device",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="192.168.1.100",
            model="SPEM-003CEBEU",
        )

        assert server.device_name == "Test Device"
        assert server.mac_address == "AABBCCDDEEFF"  # Without colons, uppercase
        assert server.http_port == 80
        assert server.host == "192.168.1.100"
        assert server.model == "SPEM-003CEBEU"
        assert server.daemon is True
        assert server.zeroconf is None
        assert server.service_info is None

    def test_init_default_model(self):
        """Test MDNSServer initialization with default model."""
        server = MDNSServer(
            device_name="Test Device",
            mac_address="aa:bb:cc:dd:ee:ff",
            http_port=8080,
        )

        assert server.model == "SPEM-003CEBEU"
        assert server.host == ""
        assert server.mac_address == "AABBCCDDEEFF"

    def test_get_local_ip_success(self):
        """Test get_local_ip with successful socket connection."""
        server = MDNSServer("Test", "AA:BB:CC:DD:EE:FF", 80)

        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket.getsockname.return_value = ("192.168.1.50", 12345)
            mock_socket_class.return_value = mock_socket

            ip = server.get_local_ip()

            assert ip == "192.168.1.50"
            mock_socket.connect.assert_called_once_with(("10.255.255.255", 1))
            mock_socket.close.assert_called_once()

    def test_get_local_ip_fallback(self):
        """Test get_local_ip fallback on exception."""
        server = MDNSServer("Test", "AA:BB:CC:DD:EE:FF", 80)

        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket.connect.side_effect = Exception("Network error")
            mock_socket_class.return_value = mock_socket

            ip = server.get_local_ip()

            assert ip == "127.0.0.1"
            mock_socket.close.assert_called_once()

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_run_with_configured_host(self, mock_service_info, mock_zeroconf_class):
        """Test run method with configured host."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="192.168.1.100",
        )

        mock_zeroconf = MagicMock()
        mock_zeroconf_class.return_value = mock_zeroconf

        server.run()

        # Should use configured host
        mock_zeroconf_class.assert_called_once()
        call_kwargs = mock_zeroconf_class.call_args[1]
        assert call_kwargs["interfaces"] == ["192.168.1.100"]

        # Should register both services
        assert mock_zeroconf.register_service.call_count == 2

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_run_with_auto_detect_host(self, mock_service_info, mock_zeroconf_class):
        """Test run method with auto-detected host."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="",  # Empty = auto-detect
        )

        mock_zeroconf = MagicMock()
        mock_zeroconf_class.return_value = mock_zeroconf

        with patch.object(server, "get_local_ip", return_value="192.168.1.50"):
            server.run()

        call_kwargs = mock_zeroconf_class.call_args[1]
        assert call_kwargs["interfaces"] == ["192.168.1.50"]

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_run_with_0000_host(self, mock_service_info, mock_zeroconf_class):
        """Test run method with 0.0.0.0 host triggers auto-detect."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="0.0.0.0",
        )

        mock_zeroconf = MagicMock()
        mock_zeroconf_class.return_value = mock_zeroconf

        with patch.object(server, "get_local_ip", return_value="10.0.0.5"):
            server.run()

        call_kwargs = mock_zeroconf_class.call_args[1]
        assert call_kwargs["interfaces"] == ["10.0.0.5"]

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_run_zeroconf_interface_fallback(
        self, mock_service_info, mock_zeroconf_class
    ):
        """Test run method falls back to default Zeroconf on interface error."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="192.168.1.100",
        )

        # First call raises exception, second call succeeds
        mock_zeroconf = MagicMock()
        mock_zeroconf_class.side_effect = [Exception("Interface error"), mock_zeroconf]

        server.run()

        # Should be called twice - first with interface, then without
        assert mock_zeroconf_class.call_count == 2

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_run_service_registration_failure(
        self, mock_service_info, mock_zeroconf_class
    ):
        """Test run method handles service registration failure."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="192.168.1.100",
        )

        mock_zeroconf = MagicMock()
        mock_zeroconf.register_service.side_effect = Exception("Registration failed")
        mock_zeroconf_class.return_value = mock_zeroconf

        # Should not raise, just log error
        server.run()

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_run_creates_correct_service_names(
        self, mock_service_info, mock_zeroconf_class
    ):
        """Test that correct service names are created."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="192.168.1.100",
        )

        mock_zeroconf = MagicMock()
        mock_zeroconf_class.return_value = mock_zeroconf

        server.run()

        # Check ServiceInfo calls
        calls = mock_service_info.call_args_list
        assert len(calls) == 2

        # First call should be for _shelly._tcp.local.
        shelly_call = calls[0]
        assert shelly_call[0][0] == "_shelly._tcp.local."
        assert "shellypro3em-ddeeff" in shelly_call[0][1].lower()

        # Second call should be for _http._tcp.local.
        http_call = calls[1]
        assert http_call[0][0] == "_http._tcp.local."
        assert "shellypro3em-ddeeff" in http_call[0][1].lower()

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_run_service_properties(self, mock_service_info, mock_zeroconf_class):
        """Test that service properties are correct."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=8080,
            host="192.168.1.100",
            model="TEST-MODEL",
        )

        mock_zeroconf = MagicMock()
        mock_zeroconf_class.return_value = mock_zeroconf

        server.run()

        # Check properties in ServiceInfo call
        call_kwargs = mock_service_info.call_args_list[0][1]
        props = call_kwargs["properties"]

        assert props["mac"] == "AABBCCDDEEFF"
        assert props["model"] == "TEST-MODEL"
        assert props["gen"] == "2"
        assert props["app"] == "Pro3EM"
        assert props["auth_en"] == "false"
        assert props["discoverable"] == "true"
        assert call_kwargs["port"] == 8080

    def test_stop_no_zeroconf(self):
        """Test stop method when zeroconf is not initialized."""
        server = MDNSServer("Test", "AA:BB:CC:DD:EE:FF", 80)

        # Should not raise
        server.stop()

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_stop_with_zeroconf(self, mock_service_info, mock_zeroconf_class):
        """Test stop method unregisters services and closes zeroconf."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="192.168.1.100",
        )

        mock_zeroconf = MagicMock()
        mock_zeroconf_class.return_value = mock_zeroconf

        server.run()
        server.stop()

        assert mock_zeroconf.unregister_service.call_count == 2
        mock_zeroconf.close.assert_called_once()

    @patch("src.servers.mdns_server.Zeroconf")
    @patch("src.servers.mdns_server.ServiceInfo")
    def test_stop_handles_unregister_error(
        self, mock_service_info, mock_zeroconf_class
    ):
        """Test stop method handles unregister errors gracefully."""
        server = MDNSServer(
            device_name="Test",
            mac_address="AA:BB:CC:DD:EE:FF",
            http_port=80,
            host="192.168.1.100",
        )

        mock_zeroconf = MagicMock()
        mock_zeroconf.unregister_service.side_effect = Exception("Unregister error")
        mock_zeroconf_class.return_value = mock_zeroconf

        server.run()

        # Should not raise
        server.stop()
