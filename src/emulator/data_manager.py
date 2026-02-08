"""Data manager for caching and synchronizing meter data."""

import dataclasses
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from ..config import get_logger, Settings, TotalsConfig
from ..data_sources import HomeAssistantClient, discover_dsmr_entities

logger = get_logger(__name__)


@dataclass
class PhaseData:
    """Data for a single phase."""

    voltage: float = 230.0  # V
    current: float = 0.0  # A
    power: float = 0.0  # W (positive = consumption, negative = production)
    power_returned: float = 0.0  # W
    apparent_power: float = 0.0  # VA
    power_factor: float = 1.0
    frequency: float = 50.0  # Hz

    # Energy totals (Wh)
    energy_total: float = 0.0
    energy_returned_total: float = 0.0

    @property
    def active_power(self) -> float:
        """Net active power (consumption - production)."""
        return self.power - self.power_returned

    def calculate_derived(self) -> None:
        """Calculate derived values from primary measurements."""
        # Apparent power: magnitude = V × I, sign follows active power
        # direction (negative = export) to match real Shelly Pro 3EM.
        if self.apparent_power == 0.0 and self.voltage > 0:
            magnitude = self.voltage * abs(self.current)
            sign = -1 if self.active_power < 0 else 1
            self.apparent_power = sign * magnitude

        if abs(self.apparent_power) > 0:
            self.power_factor = min(1.0, abs(self.active_power) / abs(self.apparent_power))


DATA_STALE_TIMEOUT = 120  # seconds before data is considered stale


@dataclass
class MeterData:
    """Complete meter data."""

    phase_a: PhaseData = field(default_factory=PhaseData)
    phase_b: PhaseData = field(default_factory=PhaseData)
    phase_c: PhaseData = field(default_factory=PhaseData)

    # Totals
    total_energy: float = 0.0  # Wh
    total_energy_returned: float = 0.0  # Wh

    # Metadata
    timestamp: float = 0.0
    is_valid: bool = False

    @property
    def is_stale(self) -> bool:
        """Check if data is too old to be considered reliable."""
        return self.timestamp > 0 and (time.time() - self.timestamp) > DATA_STALE_TIMEOUT

    @property
    def total_power(self) -> float:
        """Total active power across all phases."""
        return (
            self.phase_a.active_power
            + self.phase_b.active_power
            + self.phase_c.active_power
        )

    @property
    def total_current(self) -> float:
        """Total current across all phases."""
        return self.phase_a.current + self.phase_b.current + self.phase_c.current

    @property
    def total_apparent_power(self) -> float:
        """Total apparent power across all phases."""
        return (
            self.phase_a.apparent_power
            + self.phase_b.apparent_power
            + self.phase_c.apparent_power
        )


def build_em_status(meter_data: MeterData, em_id: int = 0) -> dict:
    """Build the EM component status dict from meter data.

    Args:
        meter_data: Current meter data.
        em_id: EM component ID (default 0).

    Returns:
        Dictionary with EM status fields.
    """
    no_data = not meter_data or not meter_data.is_valid or meter_data.is_stale
    errors = ["power_meter_failure"] if no_data else []

    pa = meter_data.phase_a if not no_data else None
    pb = meter_data.phase_b if not no_data else None
    pc = meter_data.phase_c if not no_data else None

    return {
        "id": em_id,
        "a_current": round(pa.current, 3) if pa else 0.0,
        "a_voltage": round(pa.voltage, 1) if pa else 0.0,
        "a_act_power": round(pa.active_power, 1) if pa else 0.0,
        "a_aprt_power": round(pa.apparent_power, 1) if pa else 0.0,
        "a_pf": round(pa.power_factor, 2) if pa else 0.0,
        "a_freq": round(pa.frequency, 1) if pa else 0.0,
        "a_errors": [],
        "b_current": round(pb.current, 3) if pb else 0.0,
        "b_voltage": round(pb.voltage, 1) if pb else 0.0,
        "b_act_power": round(pb.active_power, 1) if pb else 0.0,
        "b_aprt_power": round(pb.apparent_power, 1) if pb else 0.0,
        "b_pf": round(pb.power_factor, 2) if pb else 0.0,
        "b_freq": round(pb.frequency, 1) if pb else 0.0,
        "b_errors": [],
        "c_current": round(pc.current, 3) if pc else 0.0,
        "c_voltage": round(pc.voltage, 1) if pc else 0.0,
        "c_act_power": round(pc.active_power, 1) if pc else 0.0,
        "c_aprt_power": round(pc.apparent_power, 1) if pc else 0.0,
        "c_pf": round(pc.power_factor, 2) if pc else 0.0,
        "c_freq": round(pc.frequency, 1) if pc else 0.0,
        "c_errors": [],
        "n_current": None,
        "n_errors": [],
        "total_current": round(meter_data.total_current, 3) if not no_data else 0.0,
        "total_act_power": round(meter_data.total_power, 1) if not no_data else 0.0,
        "total_aprt_power": round(meter_data.total_apparent_power, 1) if not no_data else 0.0,
        "user_calibrated_phase": [],
        "errors": errors,
    }


class DataManager:
    """Manages meter data fetching and caching."""

    def __init__(self, settings: Settings):
        """Initialize the data manager.

        Args:
            settings: Application settings.
        """
        self._settings = settings
        self._data = MeterData()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        # Track last_updated timestamps per entity to sync with P1 meter updates
        self._last_timestamps: dict[str, Optional[str]] = {}

        # Initialize Home Assistant client
        ha_config = settings.homeassistant
        self._ha_client = HomeAssistantClient(
            url=ha_config.url,
            token=ha_config.token,
            use_https=ha_config.use_https,
            verify_ssl=ha_config.verify_ssl,
            timeout=ha_config.timeout,
        )

    def start(self) -> None:
        """Start the background polling thread."""
        if self._poll_thread is not None:
            return

        # Run auto-discovery if enabled
        if self._settings.dsmr.auto_discover:
            self._run_discovery()

        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("Data manager started")

    def _needs_discovery(self) -> bool:
        """Check if auto-discovery should be retried."""
        return (
            self._settings.dsmr.auto_discover
            and not self._settings.dsmr.has_any_entity()
        )

    def _run_discovery(self) -> None:
        """Run DSMR entity auto-discovery."""
        ha_config = self._settings.homeassistant

        logger.info("Running DSMR entity auto-discovery...")

        try:
            discovered = discover_dsmr_entities(
                url=ha_config.url,
                token=ha_config.token,
                use_https=ha_config.use_https,
                verify_ssl=ha_config.verify_ssl,
            )

            if not discovered.has_power_data():
                logger.warning(
                    "No DSMR power entities discovered",
                    hint="Check Home Assistant DSMR integration or configure entities manually",
                )
                return

            # Build configuration from discovered entities
            single_phase = None
            three_phase = None

            if discovered.is_three_phase:
                three_phase = {
                    "phase_a": {
                        "voltage": discovered.phase_a.voltage,
                        "current": discovered.phase_a.current,
                        "power": discovered.phase_a.power,
                        "power_returned": discovered.phase_a.power_returned,
                    },
                    "phase_b": {
                        "voltage": discovered.phase_b.voltage,
                        "current": discovered.phase_b.current,
                        "power": discovered.phase_b.power,
                        "power_returned": discovered.phase_b.power_returned,
                    },
                    "phase_c": {
                        "voltage": discovered.phase_c.voltage,
                        "current": discovered.phase_c.current,
                        "power": discovered.phase_c.power,
                        "power_returned": discovered.phase_c.power_returned,
                    },
                }
                logger.info(
                    "Discovered three-phase configuration",
                    phase_a_power=discovered.phase_a.power,
                    phase_b_power=discovered.phase_b.power,
                    phase_c_power=discovered.phase_c.power,
                )
            else:
                single_phase = {
                    "power": discovered.power_total,
                    "power_returned": discovered.power_returned_total,
                }
                logger.info(
                    "Discovered single-phase configuration",
                    power=discovered.power_total,
                )

            totals = TotalsConfig(
                energy_delivered=discovered.totals.energy_delivered,
                energy_returned=discovered.totals.energy_returned,
                energy_delivered_tariff_1=discovered.totals.energy_delivered_tariff_1,
                energy_delivered_tariff_2=discovered.totals.energy_delivered_tariff_2,
                energy_returned_tariff_1=discovered.totals.energy_returned_tariff_1,
                energy_returned_tariff_2=discovered.totals.energy_returned_tariff_2,
            )

            # Update settings with discovered entities
            self._settings.dsmr.set_discovered_entities(
                single_phase=single_phase,
                three_phase=three_phase,
                totals=totals,
                is_three_phase=discovered.is_three_phase,
            )

            logger.info(
                "DSMR auto-discovery completed successfully",
                is_three_phase=discovered.is_three_phase,
            )

            # Log the discovered entities for debugging
            if discovered.is_three_phase:
                logger.info(
                    "Phase A entities",
                    power=discovered.phase_a.power or "(not found)",
                    power_returned=discovered.phase_a.power_returned or "(not found)",
                    current=discovered.phase_a.current or "(not found)",
                    voltage=discovered.phase_a.voltage or "(not found)",
                )
                logger.info(
                    "Phase B entities",
                    power=discovered.phase_b.power or "(not found)",
                    power_returned=discovered.phase_b.power_returned or "(not found)",
                    current=discovered.phase_b.current or "(not found)",
                    voltage=discovered.phase_b.voltage or "(not found)",
                )
                logger.info(
                    "Phase C entities",
                    power=discovered.phase_c.power or "(not found)",
                    power_returned=discovered.phase_c.power_returned or "(not found)",
                    current=discovered.phase_c.current or "(not found)",
                    voltage=discovered.phase_c.voltage or "(not found)",
                )
            else:
                logger.info(
                    "Single phase entities",
                    power=discovered.power_total or "(not found)",
                    power_returned=discovered.power_returned_total or "(not found)",
                )

        except Exception as e:
            logger.error("DSMR auto-discovery failed", error=str(e))

    def stop(self) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=5.0)
            self._poll_thread = None
        self._ha_client.close()
        logger.info("Data manager stopped")

    def get_data(self) -> MeterData:
        """Get the current meter data.

        Returns:
            Copy of current meter data.
        """
        with self._lock:
            return dataclasses.replace(
                self._data,
                phase_a=dataclasses.replace(self._data.phase_a),
                phase_b=dataclasses.replace(self._data.phase_b),
                phase_c=dataclasses.replace(self._data.phase_c),
            )

    def _poll_loop(self) -> None:
        """Background polling loop."""
        poll_interval = self._settings.homeassistant.poll_interval
        discovery_retry_interval = 30  # seconds between discovery retries
        last_discovery_time: float = 0.0

        while not self._stop_event.is_set():
            # Retry auto-discovery if no entities configured yet
            if self._needs_discovery():
                now = time.time()
                if now - last_discovery_time >= discovery_retry_interval:
                    logger.info(
                        "Retrying DSMR auto-discovery (no entities configured yet)",
                    )
                    self._run_discovery()
                    last_discovery_time = now

            try:
                self._fetch_data()
            except Exception as e:
                logger.error("Error fetching data", error=str(e))
                # Mark data as invalid if fetch fails and data is stale
                with self._lock:
                    if self._data.is_stale:
                        self._data.is_valid = False

            self._stop_event.wait(poll_interval)

    def _fetch_data(self) -> None:
        """Fetch data from Home Assistant.

        Fetches all power entities via get_entity_with_unit() (single request per entity),
        tracks their timestamps, and skips updating cached data if nothing changed.
        """
        dsmr = self._settings.dsmr

        new_data = MeterData()
        new_data.timestamp = time.time()
        any_changed = False
        has_power_entities = False

        if dsmr.is_three_phase():
            for phase_name, phase_data in [
                ("phase_a", new_data.phase_a),
                ("phase_b", new_data.phase_b),
                ("phase_c", new_data.phase_c),
            ]:
                config = dsmr.get_phase_config(phase_name)
                changed = self._fetch_phase_data(config, phase_data)
                if changed:
                    any_changed = True
                if config.power or config.power_returned:
                    has_power_entities = True
        else:
            power_entity = dsmr.get_single_phase_power()
            if power_entity:
                has_power_entities = True
                ev = self._ha_client.get_entity_with_unit(power_entity)
                if ev.converted_value is not None:
                    old_ts = self._last_timestamps.get(power_entity)
                    if ev.last_updated != old_ts:
                        any_changed = True
                        self._last_timestamps[power_entity] = ev.last_updated
                    power = ev.converted_value
                    if power >= 0:
                        new_data.phase_a.power = power
                    else:
                        new_data.phase_a.power_returned = abs(power)

        if not has_power_entities:
            logger.warning(
                "No power entities found for timestamp check, will poll every cycle."
            )

        if not any_changed and self._data.is_valid and has_power_entities:
            # No sensor changed but we can still reach HA — refresh timestamp
            # to prevent the cache from being marked stale after DATA_STALE_TIMEOUT
            with self._lock:
                self._data.timestamp = time.time()
            logger.debug("Skipping data fetch: no sensor data changed")
            return

        # Fetch energy totals (auto_convert handles kWh -> Wh conversion)
        totals = dsmr.get_totals()
        if totals.energy_delivered:
            value = self._ha_client.get_value(totals.energy_delivered)
            if value is not None:
                new_data.total_energy = value

        if totals.energy_returned:
            value = self._ha_client.get_value(totals.energy_returned)
            if value is not None:
                new_data.total_energy_returned = value

        # Handle tariff-based energy if main totals not available
        # DSMR typically uses ELECTRICITY_USED_TARIFF_1/2 and ELECTRICITY_DELIVERED_TARIFF_1/2
        if new_data.total_energy == 0:
            t1 = self._ha_client.get_value(totals.energy_delivered_tariff_1) or 0
            t2 = self._ha_client.get_value(totals.energy_delivered_tariff_2) or 0
            new_data.total_energy = t1 + t2  # Already converted by get_value

        if new_data.total_energy_returned == 0:
            t1 = self._ha_client.get_value(totals.energy_returned_tariff_1) or 0
            t2 = self._ha_client.get_value(totals.energy_returned_tariff_2) or 0
            new_data.total_energy_returned = t1 + t2

        # Calculate derived values
        for phase in [new_data.phase_a, new_data.phase_b, new_data.phase_c]:
            phase.calculate_derived()

        new_data.is_valid = self._ha_client.is_connected()

        # Update cached data
        with self._lock:
            self._data = new_data

        logger.debug(
            "Data updated",
            total_power=new_data.total_power,
            phase_a_power=new_data.phase_a.active_power,
            phase_b_power=new_data.phase_b.active_power,
            phase_c_power=new_data.phase_c.active_power,
            valid=new_data.is_valid,
        )

    def _fetch_phase_data(self, config, phase_data: PhaseData) -> bool:
        """Fetch data for a single phase.

        Uses get_entity_with_unit() for power entities to combine value fetching
        and timestamp tracking into a single request.

        Note: Many DSMR meters don't provide voltage readings. In this case,
        the default value of 230V is used. Current is often available but
        power readings are the most reliable.

        Args:
            config: Phase configuration with entity IDs.
            phase_data: PhaseData object to update.

        Returns:
            True if any power entity timestamp changed (new data available).
        """
        any_changed = False

        # Voltage (often not available in DSMR - uses default 230V)
        if config.voltage:
            value = self._ha_client.get_value(config.voltage)
            if value is not None:
                phase_data.voltage = value
        # If no voltage entity configured or unavailable, keep default (230V)

        # Current (usually available as INSTANTANEOUS_CURRENT_L1/L2/L3)
        if config.current:
            value = self._ha_client.get_value(config.current)
            if value is not None:
                phase_data.current = value

        # Active power consumption (INSTANTANEOUS_ACTIVE_POWER_Lx_POSITIVE)
        # Uses get_entity_with_unit to get value + timestamp in one request
        if config.power:
            ev = self._ha_client.get_entity_with_unit(config.power)
            if ev.converted_value is not None:
                old_ts = self._last_timestamps.get(config.power)
                if ev.last_updated != old_ts:
                    any_changed = True
                    self._last_timestamps[config.power] = ev.last_updated
                if ev.converted_value >= 0:
                    phase_data.power = ev.converted_value
                else:
                    phase_data.power_returned = abs(ev.converted_value)

        # Active power production/return (INSTANTANEOUS_ACTIVE_POWER_Lx_NEGATIVE)
        # Uses get_entity_with_unit to get value + timestamp in one request
        # (only if not already set from negative power above)
        if config.power_returned and phase_data.power_returned == 0.0:
            ev = self._ha_client.get_entity_with_unit(config.power_returned)
            if ev.converted_value is not None:
                old_ts = self._last_timestamps.get(config.power_returned)
                if ev.last_updated != old_ts:
                    any_changed = True
                    self._last_timestamps[config.power_returned] = ev.last_updated
                phase_data.power_returned = ev.converted_value

        return any_changed
