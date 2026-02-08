"""Modbus TCP server for Shelly Pro 3EM emulation."""

import threading
from typing import Optional

from pymodbus.datastore import (
    ModbusServerContext,
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
)
from pymodbus.pdu.device import ModbusDeviceIdentification
from pymodbus.server import StartTcpServer, ServerStop

from ..config import get_logger
from ..emulator.data_manager import DataManager
from ..emulator.register_map import RegisterMap
from ..emulator.shelly_device import ShellyDevice

logger = get_logger(__name__)


class CustomModbusDeviceContext(ModbusDeviceContext):
    """Custom slave context that reads from our register map."""

    def __init__(self, register_map: RegisterMap, data_manager: DataManager):
        """Initialize the custom slave context.

        Args:
            register_map: Register map for the Shelly device.
            data_manager: Data manager for meter data.
        """
        # Create minimal data blocks required by parent class
        # We override getValues/setValues so these won't be used
        empty_block = ModbusSequentialDataBlock(0, [0])
        super().__init__(
            di=empty_block,
            co=empty_block,
            hr=empty_block,
            ir=empty_block,
        )
        self._register_map = register_map
        self._data_manager = data_manager

    def getValues(self, fc_as_hex: int, address: int, count: int = 1):
        """Get register values.

        Args:
            fc_as_hex: Function code.
            address: Starting address.
            count: Number of registers.

        Returns:
            List of register values.
        """
        # Update register map with current data
        data = self._data_manager.get_data()
        self._register_map.set_data(data)

        # Read from register map
        # Modbus addresses are 0-based internally, but Shelly uses 30000+ addresses
        # We need to handle both input registers (fc=4) and holding registers (fc=3)
        actual_address = address

        # Map function codes to register ranges
        # FC 3 (holding registers) and FC 4 (input registers)
        if fc_as_hex in (3, 4):
            values = self._register_map.read_registers(actual_address, count)
            logger.debug(
                "Modbus read",
                fc=fc_as_hex,
                address=actual_address,
                count=count,
                values=values[:5] if len(values) > 5 else values,
            )
            return values

        return [0] * count

    def setValues(self, fc_as_hex: int, address: int, values: list):
        """Set register values (not implemented - read-only device)."""
        logger.warning(
            "Write attempt to read-only register",
            fc=fc_as_hex,
            address=address,
        )

    def validate(self, fc_as_hex: int, address: int, count: int = 1) -> bool:
        """Validate register access.

        Args:
            fc_as_hex: Function code.
            address: Starting address.
            count: Number of registers.

        Returns:
            True if access is valid.
        """
        # Allow reads from device info and EM/EMData registers
        if fc_as_hex in (3, 4):
            # Device info: 30000-30099
            # EM registers: 31000-31079
            # EMData registers: 31160-31229
            if 30000 <= address <= 30099:
                return True
            if 31000 <= address <= 31079:
                return True
            if 31160 <= address <= 31229:
                return True

        return False


class ModbusServer:
    """Modbus TCP server for Shelly Pro 3EM emulation."""

    def __init__(
        self,
        device: ShellyDevice,
        data_manager: DataManager,
        host: str = "0.0.0.0",
        port: int = 502,
        unit_id: int = 1,
    ):
        """Initialize the Modbus server.

        Args:
            device: Shelly device configuration.
            data_manager: Data manager for meter data.
            host: Host address to bind to.
            port: Port to listen on.
            unit_id: Modbus unit ID.
        """
        self._device = device
        self._data_manager = data_manager
        self._host = host
        self._port = port
        self._unit_id = unit_id

        self._register_map = RegisterMap(device)
        self._server_thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        """Start the Modbus server."""
        if self._running:
            return

        self._running = True
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()
        logger.info(
            "Modbus server started",
            host=self._host,
            port=self._port,
            unit_id=self._unit_id,
        )

    def stop(self) -> None:
        """Stop the Modbus server."""
        if not self._running:
            return

        self._running = False
        try:
            ServerStop()
        except Exception as e:
            logger.debug("Error stopping server", error=str(e))

        if self._server_thread:
            self._server_thread.join(timeout=5.0)
            self._server_thread = None

        logger.info("Modbus server stopped")

    def _run_server(self) -> None:
        """Run the Modbus server."""
        # Create custom slave context
        slave_context = CustomModbusDeviceContext(
            self._register_map,
            self._data_manager,
        )

        # Create server context
        context = ModbusServerContext(
            devices={self._unit_id: slave_context},
            single=False,
        )

        # Device identification
        identity = ModbusDeviceIdentification()
        identity.VendorName = "Shelly"
        identity.ProductCode = self._device.model
        identity.VendorUrl = "https://shelly.cloud"
        identity.ProductName = "Shelly Pro 3EM"
        identity.ModelName = self._device.model
        identity.MajorMinorRevision = self._device.firmware_version

        try:
            StartTcpServer(
                context=context,
                identity=identity,
                address=(self._host, self._port),
            )
        except Exception as e:
            if self._running:
                logger.error("Modbus server error", error=str(e))
