"""Shelly device definition and properties."""

import time
from dataclasses import dataclass


@dataclass
class ShellyDevice:
    """Shelly Pro 3EM device properties."""

    device_id: str
    device_name: str
    mac_address: str

    # Device model info
    model: str = "SPEM-003CEBEU"
    firmware_version: str = "1.1.0"
    fw_id: str = "20231219-133625/1.1.0-g9eb7ffd"
    hardware_version: str = "1.0"

    def __post_init__(self):
        """Validate and normalize MAC address."""
        # Normalize MAC address format
        mac = self.mac_address.replace(":", "").replace("-", "").upper()
        if len(mac) != 12:
            raise ValueError(f"Invalid MAC address: {self.mac_address}")
        self.mac_address = mac

        # Auto-derive device_id from MAC when using placeholder default
        if not self.device_id or self.device_id == "shellypro3em-emulator":
            self.device_id = f"shellypro3em-{mac[-6:].lower()}"

        self._start_time = time.time()

    @property
    def mac_bytes(self) -> bytes:
        """Get MAC address as bytes."""
        return bytes.fromhex(self.mac_address)

    @property
    def mac_formatted(self) -> str:
        """Get MAC address in colon-separated format."""
        return ":".join(self.mac_address[i : i + 2] for i in range(0, 12, 2))

    def get_device_info(self) -> dict:
        """Get device info dictionary for JSON responses."""
        return {
            "id": self.device_id,
            "mac": self.mac_address,  # No colons, uppercase (Shelly API standard)
            "model": self.model,
            "gen": 2,
            "fw_id": self.fw_id,
            "ver": self.firmware_version,
            "app": "Pro3EM",
            "auth_en": False,
            "auth_domain": None,
        }

    def get_uptime(self) -> int:
        """Returns the device uptime in seconds."""
        return int(time.time() - self._start_time)

    def get_current_time(self) -> float:
        """Returns the current Unix timestamp."""
        return time.time()
