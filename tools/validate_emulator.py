#!/usr/bin/env python3
"""
Shelly Pro 3EM Emulator Validation Script

This script validates a running Shelly Pro 3EM emulator against the official
Shelly Gen2 Modbus specification.

Usage:
    python validate_emulator.py [--host HOST] [--modbus-port PORT] [--udp-port PORT]

Example:
    python validate_emulator.py --host 192.168.1.100
    python validate_emulator.py --host localhost --modbus-port 502 --udp-port 1010
"""

import argparse
import json
import socket
import struct
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class RegisterSpec:
    """Specification for a Modbus register."""
    address: int
    size: int  # Number of 16-bit registers
    name: str
    data_type: str  # float, uint32, uint16, boolean, string
    unit: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""


# Shelly Pro 3EM Modbus Register Specification
# Based on: https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM/
DEVICE_INFO_REGISTERS = [
    RegisterSpec(30000, 3, "mac_address", "bytes", description="MAC address (6 bytes)"),
    RegisterSpec(30006, 10, "device_model", "string", description="Device model"),
    RegisterSpec(30016, 16, "device_name", "string", description="Device name"),
]

EM_REGISTERS = [
    # Timestamp and status
    RegisterSpec(31000, 2, "timestamp", "uint32", description="Timestamp of last update"),
    RegisterSpec(31002, 1, "phase_a_error", "boolean", description="Phase A meter error"),
    RegisterSpec(31003, 1, "phase_b_error", "boolean", description="Phase B meter error"),
    RegisterSpec(31004, 1, "phase_c_error", "boolean", description="Phase C meter error"),

    # Totals
    RegisterSpec(31007, 2, "neutral_current", "float", "A", 0, 100, "Neutral current"),
    RegisterSpec(31011, 2, "total_current", "float", "A", 0, 500, "Total current"),
    RegisterSpec(31013, 2, "total_active_power", "float", "W", -50000, 50000, "Total active power"),
    RegisterSpec(31015, 2, "total_apparent_power", "float", "VA", -100000, 100000, "Total apparent power"),

    # Phase A
    RegisterSpec(31020, 2, "phase_a_voltage", "float", "V", 180, 280, "Phase A voltage"),
    RegisterSpec(31022, 2, "phase_a_current", "float", "A", 0, 100, "Phase A current"),
    RegisterSpec(31024, 2, "phase_a_power", "float", "W", -20000, 20000, "Phase A active power"),
    RegisterSpec(31026, 2, "phase_a_apparent", "float", "VA", -25000, 25000, "Phase A apparent power"),
    RegisterSpec(31028, 2, "phase_a_pf", "float", None, -1, 1, "Phase A power factor"),
    RegisterSpec(31033, 2, "phase_a_freq", "float", "Hz", 45, 65, "Phase A frequency"),

    # Phase B
    RegisterSpec(31040, 2, "phase_b_voltage", "float", "V", 180, 280, "Phase B voltage"),
    RegisterSpec(31042, 2, "phase_b_current", "float", "A", 0, 100, "Phase B current"),
    RegisterSpec(31044, 2, "phase_b_power", "float", "W", -20000, 20000, "Phase B active power"),
    RegisterSpec(31046, 2, "phase_b_apparent", "float", "VA", -25000, 25000, "Phase B apparent power"),
    RegisterSpec(31048, 2, "phase_b_pf", "float", None, -1, 1, "Phase B power factor"),
    RegisterSpec(31053, 2, "phase_b_freq", "float", "Hz", 45, 65, "Phase B frequency"),

    # Phase C
    RegisterSpec(31060, 2, "phase_c_voltage", "float", "V", 180, 280, "Phase C voltage"),
    RegisterSpec(31062, 2, "phase_c_current", "float", "A", 0, 100, "Phase C current"),
    RegisterSpec(31064, 2, "phase_c_power", "float", "W", -20000, 20000, "Phase C active power"),
    RegisterSpec(31066, 2, "phase_c_apparent", "float", "VA", -25000, 25000, "Phase C apparent power"),
    RegisterSpec(31068, 2, "phase_c_pf", "float", None, -1, 1, "Phase C power factor"),
    RegisterSpec(31073, 2, "phase_c_freq", "float", "Hz", 45, 65, "Phase C frequency"),
]

EMDATA_REGISTERS = [
    RegisterSpec(31160, 2, "emdata_timestamp", "uint32", description="EMData timestamp"),
    RegisterSpec(31162, 2, "total_energy", "float", "Wh", 0, None, "Total active energy"),
    RegisterSpec(31164, 2, "total_energy_returned", "float", "Wh", 0, None, "Total returned energy"),

    # Phase A energy
    RegisterSpec(31170, 2, "phase_a_energy", "float", "Wh", 0, None, "Phase A energy"),
    RegisterSpec(31174, 2, "phase_a_energy_returned", "float", "Wh", 0, None, "Phase A returned"),

    # Phase B energy
    RegisterSpec(31190, 2, "phase_b_energy", "float", "Wh", 0, None, "Phase B energy"),
    RegisterSpec(31194, 2, "phase_b_energy_returned", "float", "Wh", 0, None, "Phase B returned"),

    # Phase C energy
    RegisterSpec(31210, 2, "phase_c_energy", "float", "Wh", 0, None, "Phase C energy"),
    RegisterSpec(31214, 2, "phase_c_energy_returned", "float", "Wh", 0, None, "Phase C returned"),
]


class ModbusClient:
    """Simple Modbus TCP client for testing."""

    def __init__(self, host: str, port: int = 502, unit_id: int = 1, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.transaction_id = 0

    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"  Connection failed: {e}")
            return False

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def read_input_registers(self, address: int, count: int) -> Optional[list]:
        """Read input registers (function code 4)."""
        if not self.sock:
            return None

        self.transaction_id += 1

        # Build Modbus TCP request
        request = struct.pack(
            ">HHHBBHH",
            self.transaction_id,
            0,  # Protocol ID
            6,  # Length
            self.unit_id,
            4,  # Function code: Read Input Registers
            address,
            count,
        )

        try:
            self.sock.send(request)
            response = self.sock.recv(1024)

            if len(response) < 9:
                return None

            _, _, length, unit, fc = struct.unpack(">HHHBB", response[:8])

            if fc == 4:
                byte_count = response[8]
                data = response[9:9 + byte_count]
                return list(struct.unpack(f">{len(data)//2}H", data))
            elif fc == 0x84:
                return None
            else:
                return None

        except Exception:
            return None


class UDPClient:
    """UDP client for JSON-RPC testing."""

    def __init__(self, host: str, port: int = 1010, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)

    def send_request(self, request: dict) -> Optional[dict]:
        try:
            data = json.dumps(request).encode()
            self.sock.sendto(data, (self.host, self.port))
            response_data, _ = self.sock.recvfrom(4096)
            return json.loads(response_data.decode())
        except Exception:
            return None

    def close(self):
        self.sock.close()


def registers_to_float(registers: list) -> float:
    """Convert two registers to float (big-endian)."""
    packed = struct.pack(">HH", registers[0], registers[1])
    return struct.unpack(">f", packed)[0]


def registers_to_uint32(registers: list) -> int:
    """Convert two registers to uint32."""
    return (registers[0] << 16) | registers[1]


def registers_to_string(registers: list) -> str:
    """Convert registers to string."""
    result = []
    for reg in registers:
        high = (reg >> 8) & 0xFF
        low = reg & 0xFF
        if high:
            result.append(chr(high))
        if low:
            result.append(chr(low))
    return "".join(result).rstrip("\x00")


def print_result(name: str, result: TestResult, value: str = "", expected: str = ""):
    """Print a formatted test result."""
    colors = {
        TestResult.PASS: "\033[92m",  # Green
        TestResult.FAIL: "\033[91m",  # Red
        TestResult.WARN: "\033[93m",  # Yellow
        TestResult.SKIP: "\033[90m",  # Gray
    }
    reset = "\033[0m"

    status = f"{colors[result]}[{result.value}]{reset}"

    if value and expected:
        print(f"  {status} {name}: {value} (expected: {expected})")
    elif value:
        print(f"  {status} {name}: {value}")
    else:
        print(f"  {status} {name}")


def validate_register(client: ModbusClient, spec: RegisterSpec) -> tuple[TestResult, str]:
    """Validate a single register against its specification."""
    registers = client.read_input_registers(spec.address, spec.size)

    if registers is None:
        return TestResult.FAIL, "Read failed"

    try:
        if spec.data_type == "float":
            value = registers_to_float(registers)
            value_str = f"{value:.2f}"
            if spec.unit:
                value_str += f" {spec.unit}"

            # Check range
            if spec.min_value is not None and value < spec.min_value:
                return TestResult.WARN, f"{value_str} (below min {spec.min_value})"
            if spec.max_value is not None and value > spec.max_value:
                return TestResult.WARN, f"{value_str} (above max {spec.max_value})"

            return TestResult.PASS, value_str

        elif spec.data_type == "uint32":
            value = registers_to_uint32(registers)
            return TestResult.PASS, str(value)

        elif spec.data_type == "uint16":
            value = registers[0]
            return TestResult.PASS, str(value)

        elif spec.data_type == "boolean":
            value = registers[0] != 0
            return TestResult.PASS, str(value)

        elif spec.data_type == "string":
            value = registers_to_string(registers)
            return TestResult.PASS, f'"{value}"'

        elif spec.data_type == "bytes":
            hex_str = ":".join(f"{r:04X}" for r in registers)
            return TestResult.PASS, hex_str

        else:
            return TestResult.SKIP, f"Unknown type: {spec.data_type}"

    except Exception as e:
        return TestResult.FAIL, f"Parse error: {e}"


def validate_udp_protocol(client: UDPClient) -> dict:
    """Validate UDP JSON-RPC protocol."""
    results = {"pass": 0, "fail": 0, "warn": 0}

    print("\n--- UDP JSON-RPC Protocol ---")

    # Test EM.GetStatus
    response = client.send_request({
        "id": 1,
        "method": "EM.GetStatus",
        "params": {"id": 0}
    })

    if response is None:
        print_result("EM.GetStatus", TestResult.FAIL, "No response")
        results["fail"] += 1
    elif "result" not in response:
        print_result("EM.GetStatus", TestResult.FAIL, "Missing 'result' field")
        results["fail"] += 1
    else:
        result = response["result"]
        required_fields = [
            "a_act_power", "b_act_power", "c_act_power", "total_act_power",
            "a_voltage", "b_voltage", "c_voltage",
            "a_current", "b_current", "c_current",
        ]

        missing = [f for f in required_fields if f not in result]
        if missing:
            print_result("EM.GetStatus", TestResult.WARN, f"Missing fields: {missing}")
            results["warn"] += 1
        else:
            total_power = result["total_act_power"]
            print_result("EM.GetStatus", TestResult.PASS, f"total_power={total_power}W")
            results["pass"] += 1

        # Validate individual values
        for field in ["a_act_power", "b_act_power", "c_act_power"]:
            if field in result:
                value = result[field]
                if isinstance(value, (int, float)):
                    print_result(f"  {field}", TestResult.PASS, f"{value}W")
                    results["pass"] += 1
                else:
                    print_result(f"  {field}", TestResult.FAIL, f"Not numeric: {value}")
                    results["fail"] += 1

        # Check voltage values
        for field in ["a_voltage", "b_voltage", "c_voltage"]:
            if field in result:
                value = result[field]
                if 180 <= value <= 280:
                    print_result(f"  {field}", TestResult.PASS, f"{value}V")
                    results["pass"] += 1
                else:
                    print_result(f"  {field}", TestResult.WARN, f"{value}V (outside 180-280V)")
                    results["warn"] += 1

    # Test EM1.GetStatus
    response = client.send_request({
        "id": 2,
        "method": "EM1.GetStatus",
        "params": {"id": 0}
    })

    if response is None:
        print_result("EM1.GetStatus", TestResult.FAIL, "No response")
        results["fail"] += 1
    elif "result" not in response or "act_power" not in response.get("result", {}):
        print_result("EM1.GetStatus", TestResult.FAIL, "Missing 'act_power' field")
        results["fail"] += 1
    else:
        power = response["result"]["act_power"]
        print_result("EM1.GetStatus", TestResult.PASS, f"act_power={power}W")
        results["pass"] += 1

    return results


def validate_modbus_registers(client: ModbusClient) -> dict:
    """Validate all Modbus registers."""
    results = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}

    print("\n--- Device Info Registers (30000-30099) ---")
    for spec in DEVICE_INFO_REGISTERS:
        result, value = validate_register(client, spec)
        print_result(f"{spec.address}: {spec.name}", result, value)
        results[result.value.lower()] += 1

    print("\n--- EM Registers (31000-31079) ---")
    for spec in EM_REGISTERS:
        result, value = validate_register(client, spec)
        desc = spec.description or spec.name
        print_result(f"{spec.address}: {desc}", result, value)
        results[result.value.lower()] += 1

    print("\n--- EMData Registers (31160-31229) ---")
    for spec in EMDATA_REGISTERS:
        result, value = validate_register(client, spec)
        desc = spec.description or spec.name
        print_result(f"{spec.address}: {desc}", result, value)
        results[result.value.lower()] += 1

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate Shelly Pro 3EM Emulator against specification"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Emulator host address (default: localhost)"
    )
    parser.add_argument(
        "--modbus-port",
        type=int,
        default=502,
        help="Modbus TCP port (default: 502)"
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=1010,
        help="UDP JSON-RPC port (default: 1010)"
    )
    parser.add_argument(
        "--skip-modbus",
        action="store_true",
        help="Skip Modbus validation"
    )
    parser.add_argument(
        "--skip-udp",
        action="store_true",
        help="Skip UDP validation"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Shelly Pro 3EM Emulator Validation")
    print("=" * 60)
    print(f"Target: {args.host}")
    print(f"Modbus Port: {args.modbus_port}")
    print(f"UDP Port: {args.udp_port}")

    total_results = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}

    # Modbus validation
    if not args.skip_modbus:
        print("\n" + "=" * 60)
        print("MODBUS TCP VALIDATION")
        print("=" * 60)

        modbus = ModbusClient(args.host, args.modbus_port)
        if modbus.connect():
            print(f"Connected to Modbus server at {args.host}:{args.modbus_port}")
            results = validate_modbus_registers(modbus)
            for k, v in results.items():
                total_results[k] += v
            modbus.close()
        else:
            print(f"Failed to connect to Modbus server at {args.host}:{args.modbus_port}")
            total_results["fail"] += 1

    # UDP validation
    if not args.skip_udp:
        print("\n" + "=" * 60)
        print("UDP JSON-RPC VALIDATION")
        print("=" * 60)

        udp = UDPClient(args.host, args.udp_port)
        print(f"Testing UDP server at {args.host}:{args.udp_port}")
        results = validate_udp_protocol(udp)
        for k, v in results.items():
            if k in total_results:
                total_results[k] += v
        udp.close()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total = sum(total_results.values())
    print(f"  Total tests: {total}")
    print(f"  \033[92mPASS: {total_results['pass']}\033[0m")
    print(f"  \033[91mFAIL: {total_results['fail']}\033[0m")
    print(f"  \033[93mWARN: {total_results['warn']}\033[0m")
    if total_results.get('skip', 0) > 0:
        print(f"  \033[90mSKIP: {total_results['skip']}\033[0m")

    if total_results['fail'] > 0:
        print("\n\033[91mValidation FAILED\033[0m")
        return 1
    elif total_results['warn'] > 0:
        print("\n\033[93mValidation PASSED with warnings\033[0m")
        return 0
    else:
        print("\n\033[92mValidation PASSED\033[0m")
        return 0


if __name__ == "__main__":
    sys.exit(main())
