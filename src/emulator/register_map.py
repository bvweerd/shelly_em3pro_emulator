"""Modbus register map for Shelly Pro 3EM.

Based on official Shelly API documentation:
https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM/
https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EMData/
"""

import struct
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from .data_manager import MeterData
from .shelly_device import ShellyDevice


class RegisterType(Enum):
    """Modbus register data types."""

    UINT16 = "uint16"
    UINT32 = "uint32"
    INT32 = "int32"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING = "string"


@dataclass
class RegisterDefinition:
    """Definition of a Modbus register."""

    address: int
    register_type: RegisterType
    size: int  # Number of 16-bit registers
    description: str
    getter: Optional[Callable[["RegisterMap"], list[int]]] = None


class RegisterMap:
    """Modbus register map for Shelly Pro 3EM emulation."""

    def __init__(self, device: ShellyDevice):
        """Initialize the register map.

        Args:
            device: Shelly device configuration.
        """
        self._device = device
        self._data: Optional[MeterData] = None

        # Build register definitions
        self._registers: dict[int, RegisterDefinition] = {}
        self._build_device_info_registers()
        self._build_em_registers()
        self._build_emdata_registers()

    def set_data(self, data: MeterData) -> None:
        """Update the meter data.

        Args:
            data: Current meter data.
        """
        self._data = data

    def read_registers(self, address: int, count: int) -> list[int]:
        """Read Modbus registers.

        Args:
            address: Starting register address.
            count: Number of registers to read.

        Returns:
            List of register values (16-bit integers).
        """
        result: list[int] = []
        current_addr = address

        while len(result) < count:
            if current_addr in self._registers:
                reg_def = self._registers[current_addr]
                if reg_def.getter:
                    values = reg_def.getter(self)
                    result.extend(values)
                    current_addr += reg_def.size
                else:
                    result.append(0)
                    current_addr += 1
            else:
                # Unknown register - return 0
                result.append(0)
                current_addr += 1

        return result[:count]

    def _build_device_info_registers(self) -> None:
        """Build device info registers (30000-30099)."""

        # MAC address (30000-30005) - 6 bytes as 3 uint16
        def get_mac(rm: "RegisterMap") -> list[int]:
            mac_bytes = rm._device.mac_bytes
            return [
                (mac_bytes[0] << 8) | mac_bytes[1],
                (mac_bytes[2] << 8) | mac_bytes[3],
                (mac_bytes[4] << 8) | mac_bytes[5],
            ]

        self._registers[30000] = RegisterDefinition(
            address=30000,
            register_type=RegisterType.UINT16,
            size=3,
            description="MAC address",
            getter=get_mac,
        )

        # Device model (30006-30015) - 20 bytes / 10 registers
        def get_model(rm: "RegisterMap") -> list[int]:
            model = rm._device.model.encode("utf-8")[:20].ljust(20, b"\x00")
            return [(model[i] << 8) | model[i + 1] for i in range(0, 20, 2)]

        self._registers[30006] = RegisterDefinition(
            address=30006,
            register_type=RegisterType.STRING,
            size=10,
            description="Device model",
            getter=get_model,
        )

        # Device name (30016-30031) - 32 bytes / 16 registers
        def get_name(rm: "RegisterMap") -> list[int]:
            name = rm._device.device_name.encode("utf-8")[:32].ljust(32, b"\x00")
            return [(name[i] << 8) | name[i + 1] for i in range(0, 32, 2)]

        self._registers[30016] = RegisterDefinition(
            address=30016,
            register_type=RegisterType.STRING,
            size=16,
            description="Device name",
            getter=get_name,
        )

    def _build_em_registers(self) -> None:
        """Build EM component registers (31000-31079)."""

        # Timestamp (31000-31001) - uint32
        def get_timestamp(rm: "RegisterMap") -> list[int]:
            ts = int(rm._data.timestamp) if rm._data else int(time.time())
            return self._uint32_to_registers(ts)

        self._registers[31000] = RegisterDefinition(
            address=31000,
            register_type=RegisterType.UINT32,
            size=2,
            description="Timestamp of last update",
            getter=get_timestamp,
        )

        # Error flags (31002-31006) - booleans
        for addr, desc in [
            (31002, "Phase A meter error"),
            (31003, "Phase B meter error"),
            (31004, "Phase C meter error"),
            (31005, "Neutral meter error"),
            (31006, "Phase sequence error"),
        ]:
            self._registers[addr] = RegisterDefinition(
                address=addr,
                register_type=RegisterType.BOOLEAN,
                size=1,
                description=desc,
                getter=lambda rm: [0],  # No errors
            )

        # Neutral current (31007-31008) - float
        self._registers[31007] = RegisterDefinition(
            address=31007,
            register_type=RegisterType.FLOAT,
            size=2,
            description="Neutral current (A)",
            getter=lambda rm: self._float_to_registers(0.0),
        )

        # More error flags (31009-31010)
        for addr in [31009, 31010]:
            self._registers[addr] = RegisterDefinition(
                address=addr,
                register_type=RegisterType.BOOLEAN,
                size=1,
                description="Error flag",
                getter=lambda rm: [0],
            )

        # Total current (31011-31012) - float
        def get_total_current(rm: "RegisterMap") -> list[int]:
            current = rm._data.total_current if rm._data else 0.0
            return self._float_to_registers(current)

        self._registers[31011] = RegisterDefinition(
            address=31011,
            register_type=RegisterType.FLOAT,
            size=2,
            description="Total current (A)",
            getter=get_total_current,
        )

        # Total active power (31013-31014) - float
        def get_total_power(rm: "RegisterMap") -> list[int]:
            power = rm._data.total_power if rm._data else 0.0
            return self._float_to_registers(power)

        self._registers[31013] = RegisterDefinition(
            address=31013,
            register_type=RegisterType.FLOAT,
            size=2,
            description="Total active power (W)",
            getter=get_total_power,
        )

        # Total apparent power (31015-31016) - float
        def get_total_apparent(rm: "RegisterMap") -> list[int]:
            power = rm._data.total_apparent_power if rm._data else 0.0
            return self._float_to_registers(power)

        self._registers[31015] = RegisterDefinition(
            address=31015,
            register_type=RegisterType.FLOAT,
            size=2,
            description="Total apparent power (VA)",
            getter=get_total_apparent,
        )

        # Build phase registers
        self._build_phase_registers(31020, "a")
        self._build_phase_registers(31040, "b")
        self._build_phase_registers(31060, "c")

    def _build_phase_registers(self, base_addr: int, phase: str) -> None:
        """Build registers for a single phase.

        Args:
            base_addr: Base address for the phase (31020, 31040, 31060).
            phase: Phase identifier (a, b, c).
        """

        def get_phase_data(rm: "RegisterMap"):
            if not rm._data:
                return None
            return getattr(rm._data, f"phase_{phase}")

        # Voltage (base+0)
        def get_voltage(rm: "RegisterMap") -> list[int]:
            pd = get_phase_data(rm)
            return self._float_to_registers(pd.voltage if pd else 230.0)

        self._registers[base_addr] = RegisterDefinition(
            address=base_addr,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} voltage (V)",
            getter=get_voltage,
        )

        # Current (base+2)
        def get_current(rm: "RegisterMap") -> list[int]:
            pd = get_phase_data(rm)
            return self._float_to_registers(pd.current if pd else 0.0)

        self._registers[base_addr + 2] = RegisterDefinition(
            address=base_addr + 2,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} current (A)",
            getter=get_current,
        )

        # Active power (base+4)
        def get_power(rm: "RegisterMap") -> list[int]:
            pd = get_phase_data(rm)
            return self._float_to_registers(pd.active_power if pd else 0.0)

        self._registers[base_addr + 4] = RegisterDefinition(
            address=base_addr + 4,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} active power (W)",
            getter=get_power,
        )

        # Apparent power (base+6)
        def get_apparent(rm: "RegisterMap") -> list[int]:
            pd = get_phase_data(rm)
            return self._float_to_registers(pd.apparent_power if pd else 0.0)

        self._registers[base_addr + 6] = RegisterDefinition(
            address=base_addr + 6,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} apparent power (VA)",
            getter=get_apparent,
        )

        # Power factor (base+8)
        def get_pf(rm: "RegisterMap") -> list[int]:
            pd = get_phase_data(rm)
            return self._float_to_registers(pd.power_factor if pd else 1.0)

        self._registers[base_addr + 8] = RegisterDefinition(
            address=base_addr + 8,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} power factor",
            getter=get_pf,
        )

        # Error flags (base+10, base+11, base+12)
        for offset in [10, 11, 12]:
            self._registers[base_addr + offset] = RegisterDefinition(
                address=base_addr + offset,
                register_type=RegisterType.BOOLEAN,
                size=1,
                description=f"Phase {phase.upper()} error flag",
                getter=lambda rm: [0],
            )

        # Frequency (base+13)
        def get_freq(rm: "RegisterMap") -> list[int]:
            pd = get_phase_data(rm)
            return self._float_to_registers(pd.frequency if pd else 50.0)

        self._registers[base_addr + 13] = RegisterDefinition(
            address=base_addr + 13,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} frequency (Hz)",
            getter=get_freq,
        )

    def _build_emdata_registers(self) -> None:
        """Build EMData component registers (31160-31229)."""

        # Timestamp (31160-31161)
        def get_timestamp(rm: "RegisterMap") -> list[int]:
            ts = int(rm._data.timestamp) if rm._data else int(time.time())
            return self._uint32_to_registers(ts)

        self._registers[31160] = RegisterDefinition(
            address=31160,
            register_type=RegisterType.UINT32,
            size=2,
            description="EMData timestamp",
            getter=get_timestamp,
        )

        # Total active energy (31162-31163)
        def get_total_energy(rm: "RegisterMap") -> list[int]:
            energy = rm._data.total_energy if rm._data else 0.0
            return self._float_to_registers(energy)

        self._registers[31162] = RegisterDefinition(
            address=31162,
            register_type=RegisterType.FLOAT,
            size=2,
            description="Total active energy (Wh)",
            getter=get_total_energy,
        )

        # Total returned energy (31164-31165)
        def get_total_returned(rm: "RegisterMap") -> list[int]:
            energy = rm._data.total_energy_returned if rm._data else 0.0
            return self._float_to_registers(energy)

        self._registers[31164] = RegisterDefinition(
            address=31164,
            register_type=RegisterType.FLOAT,
            size=2,
            description="Total returned energy (Wh)",
            getter=get_total_returned,
        )

        # Phase energy registers
        self._build_phase_energy_registers(31170, "a")
        self._build_phase_energy_registers(31190, "b")
        self._build_phase_energy_registers(31210, "c")

    def _build_phase_energy_registers(self, base_addr: int, phase: str) -> None:
        """Build energy registers for a single phase.

        Args:
            base_addr: Base address (31170, 31190, 31210).
            phase: Phase identifier (a, b, c).
        """

        def get_phase_data(rm: "RegisterMap"):
            if not rm._data:
                return None
            return getattr(rm._data, f"phase_{phase}")

        # Total active energy (base+0)
        def get_energy(rm: "RegisterMap") -> list[int]:
            pd = get_phase_data(rm)
            return self._float_to_registers(pd.energy_total if pd else 0.0)

        self._registers[base_addr] = RegisterDefinition(
            address=base_addr,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} total energy (Wh)",
            getter=get_energy,
        )

        # Total returned energy (base+4)
        def get_returned(rm: "RegisterMap") -> list[int]:
            pd = get_phase_data(rm)
            return self._float_to_registers(pd.energy_returned_total if pd else 0.0)

        self._registers[base_addr + 4] = RegisterDefinition(
            address=base_addr + 4,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} returned energy (Wh)",
            getter=get_returned,
        )

        # Perpetual counters (base+12, base+14) - same as above for now
        self._registers[base_addr + 12] = RegisterDefinition(
            address=base_addr + 12,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} perpetual energy (Wh)",
            getter=get_energy,
        )

        self._registers[base_addr + 14] = RegisterDefinition(
            address=base_addr + 14,
            register_type=RegisterType.FLOAT,
            size=2,
            description=f"Phase {phase.upper()} perpetual returned (Wh)",
            getter=get_returned,
        )

    @staticmethod
    def _float_to_registers(value: float) -> list[int]:
        """Convert a float to two 16-bit registers (big-endian).

        Args:
            value: Float value to convert.

        Returns:
            List of two 16-bit register values.
        """
        packed = struct.pack(">f", value)
        return [
            (packed[0] << 8) | packed[1],
            (packed[2] << 8) | packed[3],
        ]

    @staticmethod
    def _uint32_to_registers(value: int) -> list[int]:
        """Convert a uint32 to two 16-bit registers (big-endian).

        Args:
            value: Integer value to convert.

        Returns:
            List of two 16-bit register values.
        """
        return [
            (value >> 16) & 0xFFFF,
            value & 0xFFFF,
        ]
