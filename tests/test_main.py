"""Tests for the main module."""

import signal
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.main import ShellyEmulator, main
from src.config import Settings
from src.config.settings import (
    DSMRConfig,
    HomeAssistantConfig,
    HTTPServerConfig,
    LoggingConfig,
    MDNSServerConfig,
    ModbusServerConfig,
    ServersConfig,
    ShellyConfig,
    UDPServerConfig,
)


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        shelly=ShellyConfig(
            device_id="test-emulator",
            device_name="Test Shelly Pro 3EM",
            mac_address="AA:BB:CC:DD:EE:FF",
        ),
        servers=ServersConfig(
            modbus=ModbusServerConfig(enabled=False),
            udp=UDPServerConfig(enabled=False),
            http=HTTPServerConfig(enabled=False),
            mdns=MDNSServerConfig(enabled=False),
        ),
        homeassistant=HomeAssistantConfig(
            url="http://localhost:8123",
            token="test-token",
            poll_interval=1.0,
        ),
        dsmr=DSMRConfig(auto_discover=False),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.fixture
def mock_settings_all_servers():
    """Create mock settings with all servers enabled."""
    return Settings(
        shelly=ShellyConfig(
            device_id="test-emulator",
            device_name="Test Shelly Pro 3EM",
            mac_address="AA:BB:CC:DD:EE:FF",
        ),
        servers=ServersConfig(
            modbus=ModbusServerConfig(enabled=True, host="127.0.0.1", port=15502),
            udp=UDPServerConfig(enabled=True, host="127.0.0.1", ports=[15010]),
            http=HTTPServerConfig(enabled=True, host="127.0.0.1", port=18080),
            mdns=MDNSServerConfig(enabled=True, host="127.0.0.1"),
        ),
        homeassistant=HomeAssistantConfig(
            url="http://localhost:8123",
            token="test-token",
            poll_interval=1.0,
        ),
        dsmr=DSMRConfig(auto_discover=False),
        logging=LoggingConfig(level="INFO"),
    )


class TestShellyEmulator:
    """Tests for the ShellyEmulator class."""

    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    @patch("src.main.DataManager")
    def test_init_minimal(self, mock_dm, mock_logging, mock_load_config, mock_settings):
        """Test emulator initialization with minimal config."""
        mock_load_config.return_value = mock_settings

        emulator = ShellyEmulator(config_path="/test/config.yaml")

        assert emulator._device.device_id == "test-emulator"
        assert emulator._modbus_server is None
        assert emulator._udp_server is None
        assert emulator._http_server is None
        assert emulator._mdns_server is None
        assert not emulator.is_running

    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    @patch("src.main.DataManager")
    @patch("src.main.ModbusServer")
    @patch("src.main.UDPServer")
    @patch("src.main.HTTPServer")
    @patch("src.main.MDNSServer")
    def test_init_all_servers(
        self,
        mock_mdns,
        mock_http,
        mock_udp,
        mock_modbus,
        mock_dm,
        mock_logging,
        mock_load_config,
        mock_settings_all_servers,
    ):
        """Test emulator initialization with all servers enabled."""
        mock_load_config.return_value = mock_settings_all_servers

        emulator = ShellyEmulator()

        assert emulator._modbus_server is not None
        assert emulator._udp_server is not None
        assert emulator._http_server is not None
        assert emulator._mdns_server is not None

    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    @patch("src.main.DataManager")
    def test_start_stop(
        self, mock_dm_class, mock_logging, mock_load_config, mock_settings
    ):
        """Test starting and stopping the emulator."""
        mock_load_config.return_value = mock_settings
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm

        emulator = ShellyEmulator()

        # Start
        emulator.start()
        assert emulator.is_running
        mock_dm.start.assert_called_once()

        # Start again (should be no-op)
        emulator.start()
        assert mock_dm.start.call_count == 1

        # Stop
        emulator.stop()
        assert not emulator.is_running
        mock_dm.stop.assert_called_once()

        # Stop again (should be no-op)
        emulator.stop()
        assert mock_dm.stop.call_count == 1

    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    @patch("src.main.DataManager")
    @patch("src.main.ModbusServer")
    @patch("src.main.UDPServer")
    @patch("src.main.HTTPServer")
    @patch("src.main.MDNSServer")
    def test_start_stop_with_servers(
        self,
        mock_mdns_class,
        mock_http_class,
        mock_udp_class,
        mock_modbus_class,
        mock_dm_class,
        mock_logging,
        mock_load_config,
        mock_settings_all_servers,
    ):
        """Test starting and stopping with all servers."""
        mock_load_config.return_value = mock_settings_all_servers

        mock_modbus = MagicMock()
        mock_udp = MagicMock()
        mock_http = MagicMock()
        mock_mdns = MagicMock()
        mock_dm = MagicMock()

        mock_modbus_class.return_value = mock_modbus
        mock_udp_class.return_value = mock_udp
        mock_http_class.return_value = mock_http
        mock_mdns_class.return_value = mock_mdns
        mock_dm_class.return_value = mock_dm

        emulator = ShellyEmulator()
        emulator.start()

        mock_modbus.start.assert_called_once()
        mock_udp.start.assert_called_once()
        mock_http.start.assert_called_once()
        mock_mdns.start.assert_called_once()

        emulator.stop()

        mock_modbus.stop.assert_called_once()
        mock_udp.stop.assert_called_once()
        mock_mdns.stop.assert_called_once()

    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    @patch("src.main.DataManager")
    def test_run_with_keyboard_interrupt(
        self, mock_dm_class, mock_logging, mock_load_config, mock_settings
    ):
        """Test run method with keyboard interrupt."""
        mock_load_config.return_value = mock_settings
        mock_dm = MagicMock()
        mock_dm_class.return_value = mock_dm

        emulator = ShellyEmulator()

        # Simulate KeyboardInterrupt after a short delay
        def interrupt_after_delay():
            time.sleep(0.1)
            emulator._running = False

        interrupt_thread = threading.Thread(target=interrupt_after_delay)
        interrupt_thread.start()

        emulator.run()
        interrupt_thread.join()

        assert not emulator.is_running

    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    @patch("src.main.DataManager")
    def test_is_running_property(
        self, mock_dm_class, mock_logging, mock_load_config, mock_settings
    ):
        """Test is_running property."""
        mock_load_config.return_value = mock_settings

        emulator = ShellyEmulator()

        assert emulator.is_running is False
        emulator._running = True
        assert emulator.is_running is True


class TestMain:
    """Tests for the main() function."""

    @patch("src.main.ShellyEmulator")
    @patch("src.main.signal.signal")
    @patch("sys.argv", ["main.py"])
    def test_main_success(self, mock_signal, mock_emulator_class):
        """Test main function success path."""
        mock_emulator = MagicMock()
        mock_emulator_class.return_value = mock_emulator

        result = main()

        assert result == 0
        mock_emulator.run.assert_called_once()

    @patch("src.main.ShellyEmulator")
    @patch("src.main.signal.signal")
    @patch("sys.argv", ["main.py", "-c", "/path/to/config.yaml"])
    def test_main_with_config_arg(self, mock_signal, mock_emulator_class):
        """Test main function with config argument."""
        mock_emulator = MagicMock()
        mock_emulator_class.return_value = mock_emulator

        result = main()

        mock_emulator_class.assert_called_once_with(
            config_path="/path/to/config.yaml", verbose=False
        )
        assert result == 0

    @patch("src.main.ShellyEmulator")
    @patch("src.main.signal.signal")
    @patch("sys.argv", ["main.py", "--verbose"])
    def test_main_with_verbose(self, mock_signal, mock_emulator_class):
        """Test main function with verbose flag."""
        mock_emulator = MagicMock()
        mock_emulator_class.return_value = mock_emulator

        result = main()

        assert result == 0

    @patch("src.main.ShellyEmulator")
    @patch("src.main.signal.signal")
    @patch("sys.argv", ["main.py"])
    def test_main_exception(self, mock_signal, mock_emulator_class):
        """Test main function with exception."""
        mock_emulator = MagicMock()
        mock_emulator.run.side_effect = Exception("Test error")
        mock_emulator_class.return_value = mock_emulator

        result = main()

        assert result == 1

    @patch("src.main.ShellyEmulator")
    @patch("sys.argv", ["main.py"])
    def test_main_signal_handlers(self, mock_emulator_class):
        """Test that signal handlers are registered."""
        mock_emulator = MagicMock()
        mock_emulator_class.return_value = mock_emulator

        with patch("src.main.signal.signal") as mock_signal:
            main()

            # Check that SIGINT and SIGTERM handlers are registered
            calls = mock_signal.call_args_list
            signal_nums = [call[0][0] for call in calls]
            assert signal.SIGINT in signal_nums
            assert signal.SIGTERM in signal_nums
