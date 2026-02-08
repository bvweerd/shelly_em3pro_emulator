"""Main entry point for the Shelly Pro 3EM Emulator."""

import argparse
import signal
import sys
import time
from typing import Optional

from .config import load_config, setup_logging, get_logger
from .emulator import DataManager, ShellyDevice
from .servers import ModbusServer, UDPServer, HTTPServer, MDNSServer

logger = get_logger(__name__)


class ShellyEmulator:
    """Main emulator class that coordinates all components."""

    def __init__(self, config_path: Optional[str] = None, verbose: bool = False):
        """Initialize the emulator.

        Args:
            config_path: Path to configuration file.
            verbose: If True, override log level to DEBUG.
        """
        self._settings = load_config(config_path)

        # Setup logging
        setup_logging(
            level="DEBUG" if verbose else self._settings.logging.level,
            log_format=self._settings.logging.format,
        )

        # Create device
        self._device = ShellyDevice(
            device_id=self._settings.shelly.device_id,
            device_name=self._settings.shelly.device_name,
            mac_address=self._settings.shelly.mac_address,
        )

        # Create data manager
        self._data_manager = DataManager(self._settings)

        # Create servers
        self._modbus_server: Optional[ModbusServer] = None
        self._udp_server: Optional[UDPServer] = None
        self._http_server: Optional[HTTPServer] = None
        self._mdns_server: Optional[MDNSServer] = None

        if self._settings.servers.modbus.enabled:
            self._modbus_server = ModbusServer(
                device=self._device,
                data_manager=self._data_manager,
                host=self._settings.servers.modbus.host,
                port=self._settings.servers.modbus.port,
                unit_id=self._settings.servers.modbus.unit_id,
            )

        if self._settings.servers.udp.enabled:
            self._udp_server = UDPServer(
                device=self._device,
                data_manager=self._data_manager,
                host=self._settings.servers.udp.host,
                ports=self._settings.servers.udp.ports,
            )

        if self._settings.servers.http.enabled:
            self._http_server = HTTPServer(
                device=self._device,
                data_manager=self._data_manager,
                host=self._settings.servers.http.host,
                port=self._settings.servers.http.port,
            )

        if self._settings.servers.mdns.enabled:
            self._mdns_server = MDNSServer(
                device_name=self._device.device_name,
                mac_address=self._device.mac_address,
                http_port=self._settings.servers.http.port,
                host=self._settings.servers.mdns.host,
                model=self._device.model,
                firmware_version=self._device.firmware_version,
                fw_id=self._device.fw_id,
            )

        self._running = False

    def start(self) -> None:
        """Start the emulator."""
        if self._running:
            return

        logger.info(
            "Starting Shelly Pro 3EM Emulator",
            device_id=self._device.device_id,
            device_name=self._device.device_name,
        )

        # Start data manager
        self._data_manager.start()

        # Start servers
        if self._modbus_server:
            self._modbus_server.start()

        if self._udp_server:
            self._udp_server.start()

        if self._http_server:
            self._http_server.start()

        if self._mdns_server:
            self._mdns_server.start()

        self._running = True
        logger.info("Emulator started successfully")

    def stop(self) -> None:
        """Stop the emulator."""
        if not self._running:
            return

        logger.info("Stopping emulator...")

        # Stop servers
        if self._udp_server:
            self._udp_server.stop()

        if self._modbus_server:
            self._modbus_server.stop()

        if self._http_server:
            self._http_server.stop()

        if self._mdns_server:
            self._mdns_server.stop()

        # Stop data manager
        self._data_manager.stop()

        self._running = False
        logger.info("Emulator stopped")

    def run(self) -> None:
        """Run the emulator until interrupted."""
        self.start()

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stop()

    @property
    def is_running(self) -> bool:
        """Check if the emulator is running."""
        return self._running


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Shelly Pro 3EM Emulator for Marstek storage systems"
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="Path to configuration file (default: config/config.yaml)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Create and run emulator
    emulator = ShellyEmulator(config_path=args.config, verbose=args.verbose)

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("Received signal", signal=signum)
        emulator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        emulator.run()
        return 0
    except Exception as e:
        logger.error("Fatal error", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
