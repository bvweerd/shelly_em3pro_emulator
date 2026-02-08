"""Tests for the Modbus server module."""

import time
from unittest.mock import patch

import pytest

from src.servers.modbus_server import ModbusServer, CustomModbusDeviceContext
from src.emulator import RegisterMap


class TestCustomModbusDeviceContext:
    """Tests for the CustomModbusDeviceContext class."""

    @pytest.fixture
    def context(self, shelly_device, mock_data_manager):
        """Create a CustomModbusDeviceContext for testing."""
        register_map = RegisterMap(shelly_device)
        return CustomModbusDeviceContext(register_map, mock_data_manager)

    def test_init(self, shelly_device, mock_data_manager):
        """Test context initialization."""
        register_map = RegisterMap(shelly_device)
        context = CustomModbusDeviceContext(register_map, mock_data_manager)

        assert context._register_map is register_map
        assert context._data_manager is mock_data_manager

    def test_get_values_input_registers(
        self, context, mock_data_manager, sample_meter_data
    ):
        """Test reading input registers (FC 4)."""
        mock_data_manager.get_data.return_value = sample_meter_data

        # Read device info registers (30000-30005 = MAC address)
        values = context.getValues(4, 30000, 6)

        assert len(values) == 6
        mock_data_manager.get_data.assert_called()

    def test_get_values_holding_registers(
        self, context, mock_data_manager, sample_meter_data
    ):
        """Test reading holding registers (FC 3)."""
        mock_data_manager.get_data.return_value = sample_meter_data

        # Read EM registers
        values = context.getValues(3, 31000, 2)

        assert len(values) == 2

    def test_get_values_unsupported_fc(
        self, context, mock_data_manager, sample_meter_data
    ):
        """Test reading with unsupported function code."""
        mock_data_manager.get_data.return_value = sample_meter_data

        # FC 1 (coils) is not supported for our use case
        values = context.getValues(1, 30000, 10)

        assert values == [0] * 10

    def test_set_values_logs_warning(self, context, caplog):
        """Test that setValues logs a warning (read-only device)."""
        import logging

        with caplog.at_level(logging.WARNING):
            context.setValues(6, 30000, [1, 2, 3])

        # setValues should complete without error but the device is read-only

    def test_validate_device_info_registers(self, context):
        """Test validation of device info register range."""
        # Valid device info range (30000-30099)
        assert context.validate(4, 30000, 10) is True
        assert context.validate(4, 30050, 1) is True
        assert context.validate(4, 30099, 1) is True

        # Just outside range
        assert context.validate(4, 29999, 1) is False
        assert context.validate(4, 30100, 1) is False

    def test_validate_em_registers(self, context):
        """Test validation of EM register range."""
        # Valid EM range (31000-31079)
        assert context.validate(4, 31000, 10) is True
        assert context.validate(3, 31020, 2) is True
        assert context.validate(4, 31079, 1) is True

        # Just outside range
        assert context.validate(4, 30999, 1) is False
        assert context.validate(4, 31080, 1) is False

    def test_validate_emdata_registers(self, context):
        """Test validation of EMData register range."""
        # Valid EMData range (31160-31229)
        assert context.validate(4, 31160, 10) is True
        assert context.validate(3, 31200, 2) is True
        assert context.validate(4, 31229, 1) is True

        # Just outside range
        assert context.validate(4, 31159, 1) is False
        assert context.validate(4, 31230, 1) is False

    def test_validate_invalid_fc(self, context):
        """Test validation with invalid function codes."""
        # FC 1 (coils) and FC 2 (discrete inputs) should fail
        assert context.validate(1, 30000, 10) is False
        assert context.validate(2, 31000, 10) is False

        # FC 5, 6 (write) should fail
        assert context.validate(5, 30000, 1) is False
        assert context.validate(6, 31000, 1) is False


class TestModbusServer:
    """Tests for the ModbusServer class."""

    @pytest.fixture
    def modbus_server(self, shelly_device, mock_data_manager):
        """Create a ModbusServer for testing."""
        return ModbusServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="127.0.0.1",
            port=15502,
            unit_id=1,
        )

    def test_init(self, shelly_device, mock_data_manager):
        """Test ModbusServer initialization."""
        server = ModbusServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="192.168.1.100",
            port=1502,
            unit_id=5,
        )

        assert server._host == "192.168.1.100"
        assert server._port == 1502
        assert server._unit_id == 5
        assert server._running is False
        assert server._server_thread is None

    def test_init_defaults(self, shelly_device, mock_data_manager):
        """Test ModbusServer initialization with defaults."""
        server = ModbusServer(
            device=shelly_device,
            data_manager=mock_data_manager,
        )

        assert server._host == "0.0.0.0"
        assert server._port == 502
        assert server._unit_id == 1

    @patch("src.servers.modbus_server.StartTcpServer")
    def test_start(self, mock_start_server, modbus_server):
        """Test starting the Modbus server."""
        modbus_server.start()

        assert modbus_server._running is True
        assert modbus_server._server_thread is not None
        assert modbus_server._server_thread.daemon is True

        # Wait a moment for thread to start
        time.sleep(0.1)

        # Cleanup
        modbus_server._running = False

    @patch("src.servers.modbus_server.StartTcpServer")
    def test_start_already_running(self, mock_start_server, modbus_server):
        """Test starting when already running (should be no-op)."""
        modbus_server._running = True

        modbus_server.start()

        # Should not create a new thread
        assert modbus_server._server_thread is None

    @patch("src.servers.modbus_server.ServerStop")
    @patch("src.servers.modbus_server.StartTcpServer")
    def test_stop(self, mock_start_server, mock_server_stop, modbus_server):
        """Test stopping the Modbus server."""
        modbus_server.start()
        time.sleep(0.1)

        modbus_server.stop()

        assert modbus_server._running is False
        mock_server_stop.assert_called_once()

    @patch("src.servers.modbus_server.ServerStop")
    def test_stop_not_running(self, mock_server_stop, modbus_server):
        """Test stopping when not running (should be no-op)."""
        modbus_server.stop()

        mock_server_stop.assert_not_called()

    @patch("src.servers.modbus_server.ServerStop")
    @patch("src.servers.modbus_server.StartTcpServer")
    def test_stop_handles_server_stop_exception(
        self, mock_start_server, mock_server_stop, modbus_server
    ):
        """Test stop handles ServerStop exceptions gracefully."""
        mock_server_stop.side_effect = Exception("Stop error")

        modbus_server.start()
        time.sleep(0.1)

        # Should not raise
        modbus_server.stop()

        assert modbus_server._running is False

    @patch("src.servers.modbus_server.StartTcpServer")
    def test_run_server_creates_context(self, mock_start_server, modbus_server):
        """Test that _run_server creates proper Modbus context."""
        modbus_server._running = True

        # Call _run_server directly
        modbus_server._run_server()

        # Verify StartTcpServer was called
        mock_start_server.assert_called_once()
        call_kwargs = mock_start_server.call_args[1]

        assert "context" in call_kwargs
        assert "identity" in call_kwargs
        assert call_kwargs["address"] == ("127.0.0.1", 15502)

    @patch("src.servers.modbus_server.StartTcpServer")
    def test_run_server_identity(self, mock_start_server, modbus_server):
        """Test that device identity is set correctly."""
        modbus_server._running = True
        modbus_server._run_server()

        call_kwargs = mock_start_server.call_args[1]
        identity = call_kwargs["identity"]

        assert identity.VendorName == "Shelly"
        assert identity.ProductCode == "SPEM-003CEBEU"
        assert identity.ProductName == "Shelly Pro 3EM"

    @patch("src.servers.modbus_server.StartTcpServer")
    def test_run_server_handles_exception(self, mock_start_server, modbus_server):
        """Test that _run_server handles exceptions."""
        mock_start_server.side_effect = Exception("Server error")
        modbus_server._running = True

        # Should not raise
        modbus_server._run_server()

    @patch("src.servers.modbus_server.StartTcpServer")
    def test_run_server_exception_when_not_running(
        self, mock_start_server, modbus_server
    ):
        """Test that _run_server doesn't log error if stopped intentionally."""
        mock_start_server.side_effect = Exception("Server stopped")
        modbus_server._running = False  # Server was stopped intentionally

        # Should not raise
        modbus_server._run_server()
