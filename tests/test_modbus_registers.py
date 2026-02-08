"""Tests for Modbus register compliance with Shelly Pro 3EM spec."""

import struct
import time

import pytest

from src.emulator import MeterData, PhaseData, RegisterMap
from src.emulator.register_map import RegisterType, RegisterDefinition

from .conftest import registers_to_float, registers_to_uint32


class TestRegisterTypes:
    """Tests for RegisterType enum."""

    def test_register_types_exist(self):
        """Test that all register types are defined."""
        assert RegisterType.UINT16.value == "uint16"
        assert RegisterType.UINT32.value == "uint32"
        assert RegisterType.INT32.value == "int32"
        assert RegisterType.FLOAT.value == "float"
        assert RegisterType.BOOLEAN.value == "boolean"
        assert RegisterType.STRING.value == "string"


class TestRegisterDefinition:
    """Tests for RegisterDefinition dataclass."""

    def test_register_definition_minimal(self):
        """Test RegisterDefinition with minimal args."""
        reg = RegisterDefinition(
            address=30000,
            register_type=RegisterType.UINT16,
            size=1,
            description="Test register",
        )

        assert reg.address == 30000
        assert reg.register_type == RegisterType.UINT16
        assert reg.size == 1
        assert reg.getter is None

    def test_register_definition_with_getter(self):
        """Test RegisterDefinition with getter."""

        def my_getter(rm):
            return [42]

        reg = RegisterDefinition(
            address=31000,
            register_type=RegisterType.UINT16,
            size=1,
            description="Test",
            getter=my_getter,
        )

        assert reg.getter is not None


class TestRegisterMapEdgeCases:
    """Edge case tests for RegisterMap."""

    def test_read_unknown_register(self, register_map: RegisterMap, sample_meter_data):
        """Test reading unknown register returns zeros."""
        register_map.set_data(sample_meter_data)

        # Address 29000 is not defined
        registers = register_map.read_registers(29000, 5)

        assert len(registers) == 5
        assert all(r == 0 for r in registers)

    def test_read_partial_range(self, register_map: RegisterMap, sample_meter_data):
        """Test reading across known and unknown registers."""
        register_map.set_data(sample_meter_data)

        # Read starting at a known register but extending into unknown
        registers = register_map.read_registers(30000, 100)

        assert len(registers) == 100
        # First few should be MAC address (non-zero)
        assert registers[0] != 0

    def test_set_data_none(self, register_map: RegisterMap):
        """Test reading registers when data is None."""
        register_map.set_data(None)

        # Timestamp should still work (uses current time)
        registers = register_map.read_registers(31000, 2)
        assert len(registers) == 2

    def test_read_count_truncation(self, register_map: RegisterMap, sample_meter_data):
        """Test that read_registers respects count parameter."""
        register_map.set_data(sample_meter_data)

        # Request fewer registers than a multi-register value
        registers = register_map.read_registers(30000, 1)

        assert len(registers) == 1

    def test_read_phase_registers_no_data(self, register_map: RegisterMap):
        """Test reading phase registers when data is None."""
        register_map.set_data(None)

        # Phase A voltage (31020)
        registers = register_map.read_registers(31020, 2)
        voltage = registers_to_float(registers)
        assert voltage == 230.0  # Default value

        # Phase A current (31022)
        registers = register_map.read_registers(31022, 2)
        current = registers_to_float(registers)
        assert current == 0.0  # Default value

        # Phase A power (31024)
        registers = register_map.read_registers(31024, 2)
        power = registers_to_float(registers)
        assert power == 0.0  # Default value

        # Phase A apparent power (31026)
        registers = register_map.read_registers(31026, 2)
        apparent = registers_to_float(registers)
        assert apparent == 0.0  # Default value

        # Phase A power factor (31028)
        registers = register_map.read_registers(31028, 2)
        pf = registers_to_float(registers)
        assert pf == 1.0  # Default value

    def test_read_emdata_registers_no_data(self, register_map: RegisterMap):
        """Test reading EMData registers when data is None."""
        register_map.set_data(None)

        # Total energy (31162)
        registers = register_map.read_registers(31162, 2)
        energy = registers_to_float(registers)
        assert energy == 0.0  # Default value

    def test_read_all_phase_b_registers(
        self, register_map: RegisterMap, sample_meter_data
    ):
        """Test reading Phase B registers."""
        register_map.set_data(sample_meter_data)

        # Phase B starts at 31040
        registers = register_map.read_registers(31040, 10)
        assert len(registers) == 10

    def test_read_all_phase_c_registers(
        self, register_map: RegisterMap, sample_meter_data
    ):
        """Test reading Phase C registers."""
        register_map.set_data(sample_meter_data)

        # Phase C starts at 31060
        registers = register_map.read_registers(31060, 10)
        assert len(registers) == 10

    def test_read_emdata_phase_energy(
        self, register_map: RegisterMap, sample_meter_data
    ):
        """Test reading EMData phase energy registers."""
        register_map.set_data(sample_meter_data)

        # Phase A energy total (31168)
        registers = register_map.read_registers(31168, 2)
        assert len(registers) == 2

        # Phase B energy total (31176)
        registers = register_map.read_registers(31176, 2)
        assert len(registers) == 2

        # Phase C energy total (31184)
        registers = register_map.read_registers(31184, 2)
        assert len(registers) == 2


class TestDeviceInfoRegisters:
    """Test device info registers (30000-30099)."""

    def test_register_30000_mac_address(self, register_map: RegisterMap):
        """Test MAC address register returns valid bytes."""
        registers = register_map.read_registers(30000, 3)

        assert len(registers) == 3
        # MAC should be AA:BB:CC:DD:EE:FF
        assert registers[0] == 0xAABB
        assert registers[1] == 0xCCDD
        assert registers[2] == 0xEEFF

    def test_register_30006_device_model(self, register_map: RegisterMap):
        """Test device model register returns string."""
        registers = register_map.read_registers(30006, 10)

        assert len(registers) == 10
        # Should start with 'SP' for SPEM-003CEBEU
        first_chars = chr(registers[0] >> 8) + chr(registers[0] & 0xFF)
        assert first_chars.startswith("SP")

    def test_register_30016_device_name(self, register_map: RegisterMap):
        """Test device name register returns string."""
        registers = register_map.read_registers(30016, 16)

        assert len(registers) == 16
        # Convert to string
        name_bytes = b"".join(struct.pack(">H", r) for r in registers)
        name = name_bytes.rstrip(b"\x00").decode("utf-8")
        assert "Test" in name or "Shelly" in name


class TestEMRegisters:
    """Test EM component registers (31000-31079)."""

    def test_register_31000_timestamp(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test timestamp register returns valid uint32."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31000, 2)

        timestamp = registers_to_uint32(registers)
        # Should be a reasonable Unix timestamp
        assert timestamp > 1700000000
        assert timestamp < 2000000000

    def test_register_31002_to_31006_error_flags(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test error flag registers return 0 (no errors)."""
        register_map.set_data(sample_meter_data)

        for addr in [31002, 31003, 31004, 31005, 31006]:
            registers = register_map.read_registers(addr, 1)
            assert registers[0] == 0, f"Error flag at {addr} should be 0"

    def test_register_31011_total_current(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test total current register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31011, 2)

        current = registers_to_float(registers)
        expected = (
            sample_meter_data.phase_a.current
            + sample_meter_data.phase_b.current
            + sample_meter_data.phase_c.current
        )
        assert abs(current - expected) < 0.1

    def test_register_31013_total_power(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test total active power register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31013, 2)

        power = registers_to_float(registers)
        expected = sample_meter_data.total_power
        assert abs(power - expected) < 1.0

    def test_register_31015_total_apparent_power(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test total apparent power register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31015, 2)

        power = registers_to_float(registers)
        expected = sample_meter_data.total_apparent_power
        assert abs(power - expected) < 1.0


class TestPhaseARegisters:
    """Test Phase A registers (31020-31039)."""

    def test_register_31020_voltage(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase A voltage register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31020, 2)

        voltage = registers_to_float(registers)
        assert abs(voltage - sample_meter_data.phase_a.voltage) < 0.1

    def test_register_31022_current(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase A current register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31022, 2)

        current = registers_to_float(registers)
        assert abs(current - sample_meter_data.phase_a.current) < 0.1

    def test_register_31024_power(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase A active power register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31024, 2)

        power = registers_to_float(registers)
        assert abs(power - sample_meter_data.phase_a.active_power) < 1.0

    def test_register_31028_power_factor(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase A power factor register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31028, 2)

        pf = registers_to_float(registers)
        assert 0 <= pf <= 1.0

    def test_register_31033_frequency(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase A frequency register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31033, 2)

        freq = registers_to_float(registers)
        assert abs(freq - 50.0) < 1.0


class TestPhaseBRegisters:
    """Test Phase B registers (31040-31059)."""

    def test_register_31040_voltage(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase B voltage register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31040, 2)

        voltage = registers_to_float(registers)
        assert abs(voltage - sample_meter_data.phase_b.voltage) < 0.1

    def test_register_31044_power(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase B active power register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31044, 2)

        power = registers_to_float(registers)
        assert abs(power - sample_meter_data.phase_b.active_power) < 1.0


class TestPhaseCRegisters:
    """Test Phase C registers (31060-31079)."""

    def test_register_31060_voltage(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase C voltage register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31060, 2)

        voltage = registers_to_float(registers)
        assert abs(voltage - sample_meter_data.phase_c.voltage) < 0.1

    def test_register_31064_power(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test Phase C active power register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31064, 2)

        power = registers_to_float(registers)
        assert abs(power - sample_meter_data.phase_c.active_power) < 1.0


class TestEMDataRegisters:
    """Test EMData component registers (31160-31229)."""

    def test_register_31160_timestamp(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test EMData timestamp register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31160, 2)

        timestamp = registers_to_uint32(registers)
        assert timestamp > 1700000000

    def test_register_31162_total_energy(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test total active energy register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31162, 2)

        energy = registers_to_float(registers)
        assert abs(energy - sample_meter_data.total_energy) < 1.0

    def test_register_31164_total_returned_energy(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
    ):
        """Test total returned energy register."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(31164, 2)

        energy = registers_to_float(registers)
        assert abs(energy - sample_meter_data.total_energy_returned) < 1.0


class TestAllRegistersReadable:
    """Test that all expected registers are readable."""

    @pytest.mark.parametrize(
        "address,size,description",
        [
            (30000, 3, "MAC address"),
            (30006, 10, "Device model"),
            (30016, 16, "Device name"),
            (31000, 2, "EM timestamp"),
            (31011, 2, "Total current"),
            (31013, 2, "Total power"),
            (31015, 2, "Total apparent power"),
            (31020, 2, "Phase A voltage"),
            (31022, 2, "Phase A current"),
            (31024, 2, "Phase A power"),
            (31040, 2, "Phase B voltage"),
            (31044, 2, "Phase B power"),
            (31060, 2, "Phase C voltage"),
            (31064, 2, "Phase C power"),
            (31160, 2, "EMData timestamp"),
            (31162, 2, "Total energy"),
            (31164, 2, "Total returned energy"),
        ],
    )
    def test_register_readable(
        self,
        register_map: RegisterMap,
        sample_meter_data: MeterData,
        address: int,
        size: int,
        description: str,
    ):
        """Test that register is readable and returns expected size."""
        register_map.set_data(sample_meter_data)
        registers = register_map.read_registers(address, size)

        assert len(registers) == size, f"Failed for {description} at {address}"


class TestNegativePowerValues:
    """Test handling of negative power values (energy production)."""

    def test_negative_power_export(self, register_map: RegisterMap):
        """Test that negative power (export) is handled correctly."""
        data = MeterData(
            phase_a=PhaseData(power=0.0, power_returned=500.0),
            phase_b=PhaseData(power=0.0, power_returned=300.0),
            phase_c=PhaseData(power=0.0, power_returned=200.0),
            timestamp=time.time(),
            is_valid=True,
        )
        register_map.set_data(data)

        # Total power should be negative (export)
        registers = register_map.read_registers(31013, 2)
        power = registers_to_float(registers)

        assert power < 0, "Export power should be negative"
        assert abs(power - (-1000.0)) < 1.0
