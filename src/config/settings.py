"""Configuration settings module."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os

import yaml


@dataclass
class ShellyConfig:
    """Shelly device configuration."""

    device_id: str = "shellypro3em-emulator"
    device_name: str = "Shelly Pro 3EM Emulator"
    mac_address: str = "AA:BB:CC:DD:EE:FF"


@dataclass
class ModbusServerConfig:
    """Modbus server configuration."""

    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 502
    unit_id: int = 1


@dataclass
class UDPServerConfig:
    """UDP server configuration."""

    enabled: bool = True
    host: str = "0.0.0.0"
    ports: list[int] = field(default_factory=lambda: [1010, 2220, 22222])


@dataclass
class HTTPServerConfig:
    """HTTP server configuration."""

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 80


@dataclass
class MDNSServerConfig:
    """mDNS server configuration."""

    enabled: bool = False
    host: str = ""  # Empty string means auto-detect


@dataclass
class ServersConfig:
    """Server configurations."""

    modbus: ModbusServerConfig = field(default_factory=ModbusServerConfig)
    udp: UDPServerConfig = field(default_factory=UDPServerConfig)
    http: HTTPServerConfig = field(default_factory=HTTPServerConfig)
    mdns: MDNSServerConfig = field(default_factory=MDNSServerConfig)


@dataclass
class HomeAssistantConfig:
    """Home Assistant configuration."""

    url: str = "http://localhost:8123"
    token: str = ""
    use_https: bool = False
    verify_ssl: bool = True
    poll_interval: float = 2.0
    timeout: float = 10.0


@dataclass
class PhaseConfig:
    """Single phase entity configuration."""

    voltage: str = ""
    current: str = ""
    power: str = ""
    power_returned: str = ""


@dataclass
class TotalsConfig:
    """Energy totals configuration."""

    energy_delivered: str = ""
    energy_returned: str = ""
    energy_delivered_tariff_1: str = ""
    energy_delivered_tariff_2: str = ""
    energy_returned_tariff_1: str = ""
    energy_returned_tariff_2: str = ""


@dataclass
class DSMRConfig:
    """DSMR entity mapping configuration."""

    # Auto-discovery is enabled by default
    auto_discover: bool = True

    # Manual configuration (used when auto_discover is False)
    single_phase: Optional[dict] = None
    three_phase: Optional[dict] = None
    totals: TotalsConfig = field(default_factory=TotalsConfig)

    # Discovered configuration (populated at runtime)
    _discovered_three_phase: Optional[dict] = field(default=None, repr=False)
    _discovered_single_phase: Optional[dict] = field(default=None, repr=False)
    _discovered_totals: Optional[TotalsConfig] = field(default=None, repr=False)
    _is_discovered_three_phase: bool = field(default=False, repr=False)

    def set_discovered_entities(
        self,
        single_phase: Optional[dict],
        three_phase: Optional[dict],
        totals: TotalsConfig,
        is_three_phase: bool,
    ) -> None:
        """Set discovered entities from auto-discovery.

        Args:
            single_phase: Single phase power entities.
            three_phase: Three phase entities dict.
            totals: Energy total entities.
            is_three_phase: Whether three-phase was detected.
        """
        self._discovered_single_phase = single_phase
        self._discovered_three_phase = three_phase
        self._discovered_totals = totals
        self._is_discovered_three_phase = is_three_phase

    def get_phase_config(self, phase: str) -> PhaseConfig:
        """Get configuration for a specific phase."""
        # Use discovered config if auto_discover is enabled and we have discovered data
        phase_dict = self._get_active_three_phase()

        if phase_dict and phase in phase_dict:
            phase_data = phase_dict[phase]
            return PhaseConfig(
                voltage=phase_data.get("voltage", ""),
                current=phase_data.get("current", ""),
                power=phase_data.get("power", ""),
                power_returned=phase_data.get("power_returned", ""),
            )
        return PhaseConfig()

    def get_single_phase_power(self) -> str:
        """Get single phase power entity."""
        single = self._get_active_single_phase()
        if single:
            return single.get("power", "")
        return ""

    def get_totals(self) -> TotalsConfig:
        """Get energy totals configuration."""
        if self.auto_discover and self._discovered_totals:
            return self._discovered_totals
        return self.totals

    def is_three_phase(self) -> bool:
        """Check if three-phase configuration is used."""
        if self.auto_discover and self._discovered_three_phase is not None:
            return self._is_discovered_three_phase

        return self.three_phase is not None and len(self.three_phase) > 0

    def _get_active_three_phase(self) -> Optional[dict]:
        """Get the active three-phase configuration."""
        if self.auto_discover and self._discovered_three_phase:
            return self._discovered_three_phase
        return self.three_phase

    def _get_active_single_phase(self) -> Optional[dict]:
        """Get the active single-phase configuration."""
        if self.auto_discover and self._discovered_single_phase:
            return self._discovered_single_phase
        return self.single_phase

    def has_any_entity(self) -> bool:
        """Check if any entity is configured (discovered or manual)."""
        if self._discovered_single_phase or self._discovered_three_phase:
            return True
        if self.single_phase and self.single_phase.get("power"):
            return True
        if self.three_phase:
            for phase in self.three_phase.values():
                if isinstance(phase, dict) and phase.get("power"):
                    return True
        return False


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class Settings:
    """Application settings."""

    shelly: ShellyConfig = field(default_factory=ShellyConfig)
    servers: ServersConfig = field(default_factory=ServersConfig)
    homeassistant: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)
    dsmr: DSMRConfig = field(default_factory=DSMRConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(config_path: Optional[str] = None) -> Settings:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, looks for config.yaml
                    in current directory or uses defaults.

    Returns:
        Settings object with loaded configuration.
    """
    if config_path is None:
        config_path = os.environ.get("CONFIG_PATH", "config/config.yaml")

    path = Path(config_path)

    if not path.exists():
        # Try alternative locations
        alt_paths = [
            Path("config.yaml"),
            Path("/app/config/config.yaml"),
            Path.home() / ".config" / "shelly-emulator" / "config.yaml",
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                path = alt_path
                break

    if not path.exists():
        # Return defaults
        return Settings()

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    return _parse_config(data)


def _parse_config(data: dict) -> Settings:
    """Parse configuration dictionary into Settings object."""
    settings = Settings()

    # Parse shelly config
    if "shelly" in data:
        shelly_data = data["shelly"]
        settings.shelly = ShellyConfig(
            device_id=shelly_data.get("device_id", settings.shelly.device_id),
            device_name=shelly_data.get("device_name", settings.shelly.device_name),
            mac_address=shelly_data.get("mac_address", settings.shelly.mac_address),
        )

    # Parse servers config
    if "servers" in data:
        servers_data = data["servers"]

        if "modbus" in servers_data:
            mb_data = servers_data["modbus"]
            settings.servers.modbus = ModbusServerConfig(
                enabled=mb_data.get("enabled", True),
                host=mb_data.get("host", "0.0.0.0"),
                port=mb_data.get("port", 502),
                unit_id=mb_data.get("unit_id", 1),
            )

        if "udp" in servers_data:
            udp_data = servers_data["udp"]
            settings.servers.udp = UDPServerConfig(
                enabled=udp_data.get("enabled", True),
                host=udp_data.get("host", "0.0.0.0"),
                ports=udp_data.get("ports", [1010, 2220]),
            )

        if "http" in servers_data:
            http_data = servers_data["http"]
            settings.servers.http = HTTPServerConfig(
                enabled=http_data.get("enabled", settings.servers.http.enabled),
                host=http_data.get("host", settings.servers.http.host),
                port=http_data.get("port", settings.servers.http.port),
            )

        if "mdns" in servers_data:
            mdns_data = servers_data["mdns"]
            settings.servers.mdns = MDNSServerConfig(
                enabled=mdns_data.get("enabled", settings.servers.mdns.enabled),
                host=mdns_data.get("host", settings.servers.mdns.host),
            )

    # Parse Home Assistant config
    if "homeassistant" in data:
        ha_data = data["homeassistant"]
        settings.homeassistant = HomeAssistantConfig(
            url=ha_data.get("url", "http://localhost:8123"),
            token=ha_data.get("token", ""),
            use_https=ha_data.get("use_https", False),
            verify_ssl=ha_data.get("verify_ssl", True),
            poll_interval=ha_data.get("poll_interval", 2.0),
            timeout=ha_data.get("timeout", 10.0),
        )

    # Parse DSMR config
    if "dsmr" in data:
        dsmr_data = data["dsmr"]
        totals_data = dsmr_data.get("totals", {})

        settings.dsmr = DSMRConfig(
            auto_discover=dsmr_data.get("auto_discover", True),
            single_phase=dsmr_data.get("single_phase"),
            three_phase=dsmr_data.get("three_phase"),
            totals=TotalsConfig(
                energy_delivered=totals_data.get("energy_delivered", ""),
                energy_returned=totals_data.get("energy_returned", ""),
                energy_delivered_tariff_1=totals_data.get(
                    "energy_delivered_tariff_1", ""
                ),
                energy_delivered_tariff_2=totals_data.get(
                    "energy_delivered_tariff_2", ""
                ),
                energy_returned_tariff_1=totals_data.get(
                    "energy_returned_tariff_1", ""
                ),
                energy_returned_tariff_2=totals_data.get(
                    "energy_returned_tariff_2", ""
                ),
            ),
        )

    # Parse logging config
    if "logging" in data:
        log_data = data["logging"]
        settings.logging = LoggingConfig(
            level=log_data.get("level", "INFO"),
            format=log_data.get("format", settings.logging.format),
        )

    return settings
