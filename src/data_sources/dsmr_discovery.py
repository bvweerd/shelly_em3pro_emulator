"""Automatic DSMR entity discovery from Home Assistant."""

import re
from dataclasses import dataclass, field

import httpx

from ..config import get_logger

logger = get_logger(__name__)


# Common DSMR entity patterns
# Based on actual Home Assistant DSMR integration entity naming
# Supports: DSMR 5.0 (NL), DSMR 4.2 (NL), DSMR 4.0 (BE/Fluvius), Luxembourg meters
#
# OBIS Code Reference (electricity):
#   1-0:1.7.0  - Total power delivered (consumption)
#   1-0:2.7.0  - Total power returned (production)
#   1-0:21.7.0 - Instantaneous power L1+ (consumption)
#   1-0:22.7.0 - Instantaneous power L1- (production)
#   1-0:41.7.0 - Instantaneous power L2+ (consumption)
#   1-0:42.7.0 - Instantaneous power L2- (production)
#   1-0:61.7.0 - Instantaneous power L3+ (consumption)
#   1-0:62.7.0 - Instantaneous power L3- (production)
#   1-0:31.7.0 - Instantaneous current L1
#   1-0:51.7.0 - Instantaneous current L2
#   1-0:71.7.0 - Instantaneous current L3
#   1-0:32.7.0 - Instantaneous voltage L1
#   1-0:52.7.0 - Instantaneous voltage L2
#   1-0:72.7.0 - Instantaneous voltage L3
#   1-0:1.8.1  - Energy delivered tariff 1
#   1-0:1.8.2  - Energy delivered tariff 2
#   1-0:2.8.1  - Energy returned tariff 1
#   1-0:2.8.2  - Energy returned tariff 2
#
DSMR_PATTERNS = {
    # Total power consumption/production (OBIS 1-0:1.7.0 / 1-0:2.7.0)
    # CURRENT_ELECTRICITY_USAGE / CURRENT_ELECTRICITY_DELIVERY
    "power_consumption": [
        r"sensor\..*power_consumption$",
        r"sensor\..*electricity.*power_consumption$",
        r"sensor\..*current_electricity_usage$",
        r"sensor\..*power_delivered$",  # HA DSMR standard naming
        r"sensor\.dsmr.*power$",
        r"sensor\..*elektriciteit.*vermogen$",  # Dutch
        r"sensor\..*fluvius.*consumption$",  # Belgian Fluvius
        r"sensor\..*electricite.*puissance$",  # French/Luxembourg
    ],
    "power_production": [
        r"sensor\..*power_production$",
        r"sensor\..*electricity.*power_production$",
        r"sensor\..*current_electricity_delivery$",
        r"sensor\..*power_returned$",  # HA DSMR standard naming
        r"sensor\..*teruglevering$",  # Dutch
        r"sensor\..*fluvius.*production$",  # Belgian Fluvius
        r"sensor\..*electricite.*injection$",  # French/Luxembourg
    ],
    # Per-phase power patterns (OBIS 1-0:21.7.0, 1-0:41.7.0, 1-0:61.7.0 positive)
    # INSTANTANEOUS_ACTIVE_POWER_L1/L2/L3_POSITIVE
    "power_consumption_l1": [
        r"sensor\..*power.*l1_positive$",
        r"sensor\..*instantaneous_active_power_l1_positive$",
        r"sensor\..*power_delivered_l1$",  # HA DSMR standard naming
        r"sensor\..*power_consumption.*l1$",
        r"sensor\..*power_consumption.*phase.*l1$",
        r"sensor\..*active_power_l1$",
        r"sensor\..*vermogen.*l1$",  # Dutch
    ],
    "power_consumption_l2": [
        r"sensor\..*power.*l2_positive$",
        r"sensor\..*instantaneous_active_power_l2_positive$",
        r"sensor\..*power_delivered_l2$",  # HA DSMR standard naming
        r"sensor\..*power_consumption.*l2$",
        r"sensor\..*power_consumption.*phase.*l2$",
        r"sensor\..*active_power_l2$",
        r"sensor\..*vermogen.*l2$",  # Dutch
    ],
    "power_consumption_l3": [
        r"sensor\..*power.*l3_positive$",
        r"sensor\..*instantaneous_active_power_l3_positive$",
        r"sensor\..*power_delivered_l3$",  # HA DSMR standard naming
        r"sensor\..*power_consumption.*l3$",
        r"sensor\..*power_consumption.*phase.*l3$",
        r"sensor\..*active_power_l3$",
        r"sensor\..*vermogen.*l3$",  # Dutch
    ],
    # Per-phase power returned (OBIS 1-0:22.7.0, 1-0:42.7.0, 1-0:62.7.0 negative)
    # INSTANTANEOUS_ACTIVE_POWER_L1/L2/L3_NEGATIVE
    "power_production_l1": [
        r"sensor\..*power.*l1_negative$",
        r"sensor\..*instantaneous_active_power_l1_negative$",
        r"sensor\..*power_returned_l1$",  # HA DSMR standard naming
        r"sensor\..*power_production.*l1$",
        r"sensor\..*power_returned.*l1$",
        r"sensor\..*teruglevering.*l1$",  # Dutch
    ],
    "power_production_l2": [
        r"sensor\..*power.*l2_negative$",
        r"sensor\..*instantaneous_active_power_l2_negative$",
        r"sensor\..*power_returned_l2$",  # HA DSMR standard naming
        r"sensor\..*power_production.*l2$",
        r"sensor\..*power_returned.*l2$",
        r"sensor\..*teruglevering.*l2$",  # Dutch
    ],
    "power_production_l3": [
        r"sensor\..*power.*l3_negative$",
        r"sensor\..*instantaneous_active_power_l3_negative$",
        r"sensor\..*power_returned_l3$",  # HA DSMR standard naming
        r"sensor\..*power_production.*l3$",
        r"sensor\..*power_returned.*l3$",
        r"sensor\..*teruglevering.*l3$",  # Dutch
    ],
    # Voltage patterns (OBIS 1-0:32.7.0, 1-0:52.7.0, 1-0:72.7.0)
    # Note: Often not available in DSMR (depending on meter firmware)
    "voltage_l1": [
        r"sensor\..*voltage.*l1$",
        r"sensor\..*instantaneous_voltage_l1$",
        r"sensor\..*voltage.*phase.*l1$",
        r"sensor\..*voltage_phase_l1$",  # HA DSMR standard naming
        r"sensor\..*spanning.*l1$",  # Dutch
    ],
    "voltage_l2": [
        r"sensor\..*voltage.*l2$",
        r"sensor\..*instantaneous_voltage_l2$",
        r"sensor\..*voltage.*phase.*l2$",
        r"sensor\..*voltage_phase_l2$",  # HA DSMR standard naming
        r"sensor\..*spanning.*l2$",  # Dutch
    ],
    "voltage_l3": [
        r"sensor\..*voltage.*l3$",
        r"sensor\..*instantaneous_voltage_l3$",
        r"sensor\..*voltage.*phase.*l3$",
        r"sensor\..*voltage_phase_l3$",  # HA DSMR standard naming
        r"sensor\..*spanning.*l3$",  # Dutch
    ],
    # Current patterns (OBIS 1-0:31.7.0, 1-0:51.7.0, 1-0:71.7.0)
    # INSTANTANEOUS_CURRENT_L1/L2/L3
    "current_l1": [
        r"sensor\..*current.*l1$",
        r"sensor\..*instantaneous_current_l1$",
        r"sensor\..*current.*phase.*l1$",
        r"sensor\..*current_phase_l1$",  # HA DSMR standard naming
        r"sensor\..*stroom.*l1$",  # Dutch
        r"sensor\..*courant.*l1$",  # French/Luxembourg
    ],
    "current_l2": [
        r"sensor\..*current.*l2$",
        r"sensor\..*instantaneous_current_l2$",
        r"sensor\..*current.*phase.*l2$",
        r"sensor\..*current_phase_l2$",  # HA DSMR standard naming
        r"sensor\..*stroom.*l2$",  # Dutch
        r"sensor\..*courant.*l2$",  # French/Luxembourg
    ],
    "current_l3": [
        r"sensor\..*current.*l3$",
        r"sensor\..*instantaneous_current_l3$",
        r"sensor\..*current.*phase.*l3$",
        r"sensor\..*current_phase_l3$",  # HA DSMR standard naming
        r"sensor\..*stroom.*l3$",  # Dutch
        r"sensor\..*courant.*l3$",  # French/Luxembourg
    ],
    # Energy totals (sum of tariffs or direct total)
    "energy_consumption_total": [
        r"sensor\..*energy_consumption.*total$",
        r"sensor\..*total.*energy.*consumption$",
        r"sensor\..*total_energy_import$",  # Alternative naming
        r"sensor\..*energie.*verbruik.*totaal$",  # Dutch
    ],
    "energy_production_total": [
        r"sensor\..*energy_production.*total$",
        r"sensor\..*energy_returned.*total$",
        r"sensor\..*total.*energy.*returned$",
        r"sensor\..*total_energy_export$",  # Alternative naming
        r"sensor\..*energie.*teruglevering.*totaal$",  # Dutch
    ],
    # Tariff-based energy (OBIS 1-0:1.8.1/2, 1-0:2.8.1/2)
    # ELECTRICITY_USED_TARIFF_1/2, ELECTRICITY_DELIVERED_TARIFF_1/2
    # Dutch: Tariff 1 = low (night/weekend), Tariff 2 = normal (peak)
    "energy_consumption_tariff_1": [
        r"sensor\..*energy_consumption.*tariff.*1$",
        r"sensor\..*electricity_used_tariff_1$",
        r"sensor\..*electricity.*tariff_1$",
        r"sensor\..*energy_delivered.*tariff.*1$",  # HA DSMR naming variant
        r"sensor\..*energie.*dal$",  # Dutch (low tariff)
        r"sensor\..*energie.*tarief.*1$",  # Dutch
    ],
    "energy_consumption_tariff_2": [
        r"sensor\..*energy_consumption.*tariff.*2$",
        r"sensor\..*electricity_used_tariff_2$",
        r"sensor\..*electricity.*tariff_2$",
        r"sensor\..*energy_delivered.*tariff.*2$",  # HA DSMR naming variant
        r"sensor\..*energie.*piek$",  # Dutch (peak tariff)
        r"sensor\..*energie.*tarief.*2$",  # Dutch
    ],
    "energy_production_tariff_1": [
        r"sensor\..*energy_production.*tariff.*1$",
        r"sensor\..*electricity_delivered_tariff_1$",
        r"sensor\..*energy_returned.*tariff.*1$",
        r"sensor\..*teruglevering.*dal$",  # Dutch (low tariff)
        r"sensor\..*teruglevering.*tarief.*1$",  # Dutch
    ],
    "energy_production_tariff_2": [
        r"sensor\..*energy_production.*tariff.*2$",
        r"sensor\..*electricity_delivered_tariff_2$",
        r"sensor\..*energy_returned.*tariff.*2$",
        r"sensor\..*teruglevering.*piek$",  # Dutch (peak tariff)
        r"sensor\..*teruglevering.*tarief.*2$",  # Dutch
    ],
}

@dataclass
class DiscoveredPhase:
    """Discovered entities for a single phase."""

    voltage: str = ""
    current: str = ""
    power: str = ""
    power_returned: str = ""


@dataclass
class DiscoveredTotals:
    """Discovered energy total entities."""

    energy_delivered: str = ""
    energy_returned: str = ""
    energy_delivered_tariff_1: str = ""
    energy_delivered_tariff_2: str = ""
    energy_returned_tariff_1: str = ""
    energy_returned_tariff_2: str = ""


@dataclass
class DiscoveredEntities:
    """All discovered DSMR entities."""

    # Single phase power (total)
    power_total: str = ""
    power_returned_total: str = ""

    # Three phase configuration
    phase_a: DiscoveredPhase = field(default_factory=DiscoveredPhase)
    phase_b: DiscoveredPhase = field(default_factory=DiscoveredPhase)
    phase_c: DiscoveredPhase = field(default_factory=DiscoveredPhase)

    # Energy totals
    totals: DiscoveredTotals = field(default_factory=DiscoveredTotals)

    # Metadata
    is_three_phase: bool = False
    all_entities: list = field(default_factory=list)

    def has_power_data(self) -> bool:
        """Check if any power entities were discovered."""
        return bool(
            self.power_total
            or self.phase_a.power
            or self.phase_b.power
            or self.phase_c.power
        )


class DSMRDiscovery:
    """Automatic discovery of DSMR entities from Home Assistant."""

    def __init__(
        self,
        url: str,
        token: str,
        use_https: bool = False,
        verify_ssl: bool = True,
        timeout: float = 10.0,
    ):
        """Initialize the discovery client.

        Args:
            url: Base URL of Home Assistant.
            token: Long-lived access token.
            use_https: Whether to use HTTPS.
            verify_ssl: Whether to verify SSL certificates.
            timeout: Request timeout in seconds.
        """
        self._base_url = url.rstrip("/")
        if use_https and self._base_url.startswith("http://"):
            self._base_url = self._base_url.replace("http://", "https://", 1)

        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            verify=verify_ssl,
        )

    def discover(self) -> DiscoveredEntities:
        """Discover DSMR entities from Home Assistant.

        Returns:
            DiscoveredEntities with all found DSMR entities.
        """
        result = DiscoveredEntities()

        try:
            # Fetch all entities
            response = self._client.get(f"{self._base_url}/api/states")
            response.raise_for_status()
            all_states = response.json()

            # Filter for potential DSMR entities (sensors only)
            sensors = [
                s for s in all_states if s.get("entity_id", "").startswith("sensor.")
            ]

            result.all_entities = [s["entity_id"] for s in sensors]

            logger.info(
                "Found sensors in Home Assistant",
                total=len(sensors),
            )

            # Try to find DSMR entities by pattern matching
            entity_ids = [s["entity_id"] for s in sensors]
            matched = self._match_entities(entity_ids)

            # Fill in discovered entities
            result.power_total = matched.get("power_consumption", "")
            result.power_returned_total = matched.get("power_production", "")

            # Phase A (L1)
            result.phase_a.voltage = matched.get("voltage_l1", "")
            result.phase_a.current = matched.get("current_l1", "")
            result.phase_a.power = matched.get("power_consumption_l1", "")
            result.phase_a.power_returned = matched.get("power_production_l1", "")

            # Phase B (L2)
            result.phase_b.voltage = matched.get("voltage_l2", "")
            result.phase_b.current = matched.get("current_l2", "")
            result.phase_b.power = matched.get("power_consumption_l2", "")
            result.phase_b.power_returned = matched.get("power_production_l2", "")

            # Phase C (L3)
            result.phase_c.voltage = matched.get("voltage_l3", "")
            result.phase_c.current = matched.get("current_l3", "")
            result.phase_c.power = matched.get("power_consumption_l3", "")
            result.phase_c.power_returned = matched.get("power_production_l3", "")

            # Energy totals
            result.totals.energy_delivered = matched.get("energy_consumption_total", "")
            result.totals.energy_returned = matched.get("energy_production_total", "")
            result.totals.energy_delivered_tariff_1 = matched.get(
                "energy_consumption_tariff_1", ""
            )
            result.totals.energy_delivered_tariff_2 = matched.get(
                "energy_consumption_tariff_2", ""
            )
            result.totals.energy_returned_tariff_1 = matched.get(
                "energy_production_tariff_1", ""
            )
            result.totals.energy_returned_tariff_2 = matched.get(
                "energy_production_tariff_2", ""
            )

            # Determine if three-phase (check both consumption and production entities)
            result.is_three_phase = bool(
                result.phase_a.power
                or result.phase_a.power_returned
                or result.phase_b.power
                or result.phase_b.power_returned
                or result.phase_c.power
                or result.phase_c.power_returned
            )

            self._log_discovery_results(result, matched)

        except Exception as e:
            logger.error("Error discovering DSMR entities", error=str(e))

        return result

    def _match_entities(self, entity_ids: list[str]) -> dict[str, str]:
        """Match entity IDs against DSMR patterns.

        Args:
            entity_ids: List of all entity IDs.

        Returns:
            Dictionary mapping pattern names to matched entity IDs.
        """
        matched = {}

        for pattern_name, patterns in DSMR_PATTERNS.items():
            for pattern in patterns:
                regex = re.compile(pattern, re.IGNORECASE)
                for entity_id in entity_ids:
                    if regex.match(entity_id):
                        matched[pattern_name] = entity_id
                        break
                if pattern_name in matched:
                    break

        return matched

    def _log_discovery_results(
        self,
        result: DiscoveredEntities,
        matched: dict[str, str],
    ) -> None:
        """Log the discovery results."""
        if not matched:
            logger.warning(
                "No DSMR entities discovered",
                hint="Check if DSMR integration is configured in Home Assistant",
            )
            if result.all_entities:
                logger.warning(
                    "Sensors found in Home Assistant (none matched DSMR patterns):",
                )
                for entity_id in sorted(result.all_entities):
                    logger.warning("  sensor: %s", entity_id)
            return

        logger.info(
            "DSMR entities discovered",
            count=len(matched),
            is_three_phase=result.is_three_phase,
        )

        for name, entity_id in matched.items():
            logger.debug("Discovered entity", name=name, entity_id=entity_id)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()


def discover_dsmr_entities(
    url: str,
    token: str,
    use_https: bool = False,
    verify_ssl: bool = True,
) -> DiscoveredEntities:
    """Convenience function to discover DSMR entities.

    Args:
        url: Home Assistant URL.
        token: Access token.
        use_https: Use HTTPS.
        verify_ssl: Verify SSL certificates.

    Returns:
        Discovered DSMR entities.
    """
    discovery = DSMRDiscovery(url, token, use_https, verify_ssl)
    try:
        return discovery.discover()
    finally:
        discovery.close()
