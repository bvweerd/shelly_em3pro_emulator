"""Pytest configuration and fixtures."""

import socket
import struct
import time
from typing import Generator, Optional
from unittest.mock import MagicMock

import pytest

from src.config import Settings
from src.config.settings import (
    DSMRConfig,
    HomeAssistantConfig,
    ModbusServerConfig,
    ServersConfig,
    ShellyConfig,
    UDPServerConfig,
)
from src.emulator import DataManager, MeterData, PhaseData, RegisterMap, ShellyDevice


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with non-privileged ports."""
    return Settings(
        shelly=ShellyConfig(
            device_id="test-emulator",
            device_name="Test Shelly Pro 3EM",
            mac_address="AA:BB:CC:DD:EE:FF",
        ),
        servers=ServersConfig(
            modbus=ModbusServerConfig(
                enabled=True,
                host="127.0.0.1",
                port=15502,  # Non-privileged port for testing
                unit_id=1,
            ),
            udp=UDPServerConfig(
                enabled=True,
                host="127.0.0.1",
                ports=[15010, 15220],  # Non-privileged ports for testing
            ),
        ),
        homeassistant=HomeAssistantConfig(
            url="http://localhost:8123",
            token="test-token",
            poll_interval=1.0,
        ),
        dsmr=DSMRConfig(
            auto_discover=False,
            single_phase={"power": "sensor.test_power"},
        ),
    )


@pytest.fixture
def shelly_device() -> ShellyDevice:
    """Create a test Shelly device."""
    return ShellyDevice(
        device_id="test-emulator",
        device_name="Test Shelly Pro 3EM",
        mac_address="AA:BB:CC:DD:EE:FF",
    )


@pytest.fixture
def sample_meter_data() -> MeterData:
    """Create sample meter data for testing."""
    return MeterData(
        phase_a=PhaseData(
            voltage=230.5,
            current=5.2,
            power=1150.0,
            power_returned=0.0,
            apparent_power=1196.6,
            power_factor=0.96,
            frequency=50.0,
        ),
        phase_b=PhaseData(
            voltage=231.2,
            current=3.8,
            power=850.0,
            power_returned=0.0,
            apparent_power=878.56,
            power_factor=0.97,
            frequency=50.0,
        ),
        phase_c=PhaseData(
            voltage=229.8,
            current=4.5,
            power=1000.0,
            power_returned=0.0,
            apparent_power=1034.1,
            power_factor=0.97,
            frequency=50.0,
        ),
        total_energy=15000000.0,  # 15 MWh in Wh
        total_energy_returned=5000000.0,  # 5 MWh in Wh
        timestamp=time.time(),
        is_valid=True,
    )


@pytest.fixture
def register_map(shelly_device: ShellyDevice) -> RegisterMap:
    """Create a register map for testing."""
    return RegisterMap(shelly_device)


@pytest.fixture
def mock_data_manager(test_settings: Settings, sample_meter_data: MeterData):
    """Create a mock data manager."""
    manager = MagicMock(spec=DataManager)
    manager.get_data.return_value = sample_meter_data
    return manager


class ModbusTestClient:
    """Simple Modbus TCP client for testing."""

    def __init__(self, host: str, port: int, unit_id: int = 1, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.transaction_id = 0

    def connect(self) -> bool:
        """Connect to the Modbus server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            return True
        except Exception:
            return False

    def close(self):
        """Close the connection."""
        if self.sock:
            self.sock.close()
            self.sock = None

    def read_input_registers(self, address: int, count: int) -> list[int]:
        """Read input registers (function code 4)."""
        return self._read_registers(address, count, function_code=4)

    def read_holding_registers(self, address: int, count: int) -> list[int]:
        """Read holding registers (function code 3)."""
        return self._read_registers(address, count, function_code=3)

    def _read_registers(
        self, address: int, count: int, function_code: int
    ) -> list[int]:
        """Read registers from the server."""
        if not self.sock:
            raise ConnectionError("Not connected")

        self.transaction_id += 1

        # Build Modbus TCP request
        # MBAP Header: transaction_id(2) + protocol_id(2) + length(2) + unit_id(1)
        # PDU: function_code(1) + address(2) + count(2)
        request = struct.pack(
            ">HHHBBHH",
            self.transaction_id,  # Transaction ID
            0,  # Protocol ID (Modbus)
            6,  # Length (unit_id + function_code + address + count)
            self.unit_id,  # Unit ID
            function_code,  # Function code
            address,  # Starting address
            count,  # Number of registers
        )

        self.sock.send(request)

        # Receive response
        response = self.sock.recv(1024)

        if len(response) < 9:
            raise ValueError("Invalid response length")

        # Parse MBAP header
        _, _, length, unit, fc = struct.unpack(">HHHBB", response[:8])

        if fc == function_code:
            # Success response
            byte_count = response[8]
            data = response[9 : 9 + byte_count]
            return list(struct.unpack(f">{len(data)//2}H", data))
        elif fc == function_code + 0x80:
            # Error response
            error_code = response[8]
            raise ValueError(f"Modbus error: {error_code}")
        else:
            raise ValueError(f"Unexpected function code: {fc}")


@pytest.fixture
def modbus_test_client() -> Generator[ModbusTestClient, None, None]:
    """Create a Modbus test client."""
    client = ModbusTestClient("127.0.0.1", 15502, unit_id=1)
    yield client
    client.close()


# Helper functions for register value conversion
def registers_to_float(registers: list[int]) -> float:
    """Convert two registers to a float (big-endian)."""
    if len(registers) < 2:
        raise ValueError("Need at least 2 registers")
    packed = struct.pack(">HH", registers[0], registers[1])
    return struct.unpack(">f", packed)[0]


def registers_to_uint32(registers: list[int]) -> int:
    """Convert two registers to a uint32 (big-endian)."""
    if len(registers) < 2:
        raise ValueError("Need at least 2 registers")
    return (registers[0] << 16) | registers[1]
