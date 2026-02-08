"""Home Assistant REST API client."""

from dataclasses import dataclass
from typing import Optional

import httpx

from ..config import get_logger

logger = get_logger(__name__)


# Units that need conversion to base units (W, Wh)
UNIT_CONVERSIONS = {
    "kW": 1000.0,  # kW to W
    "MW": 1000000.0,  # MW to W
    "kWh": 1000.0,  # kWh to Wh
    "MWh": 1000000.0,  # MWh to Wh
}


@dataclass
class EntityValue:
    """Value with unit information."""

    value: Optional[float]
    unit: Optional[str]
    converted_value: Optional[float]  # Value in base units (W, Wh)
    last_updated: Optional[str] = None  # ISO timestamp from Home Assistant


class HomeAssistantClient:
    """Client for fetching data from Home Assistant REST API."""

    def __init__(
        self,
        url: str,
        token: str,
        use_https: bool = False,
        verify_ssl: bool = True,
        timeout: float = 10.0,
    ):
        """Initialize the Home Assistant client.

        Args:
            url: Base URL of Home Assistant (e.g., http://192.168.1.100:8123).
            token: Long-lived access token.
            use_https: Whether to use HTTPS.
            verify_ssl: Whether to verify SSL certificates.
            timeout: Request timeout in seconds.
        """
        # Normalize URL
        self._base_url = url.rstrip("/")
        if use_https and self._base_url.startswith("http://"):
            self._base_url = self._base_url.replace("http://", "https://", 1)

        self._token = token
        self._timeout = timeout
        self._verify_ssl = verify_ssl

        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            verify=verify_ssl,
        )

        self._connected = False
        self._last_error: Optional[str] = None

    def get_value(self, entity_id: str, auto_convert: bool = True) -> Optional[float]:
        """Get the current value of a Home Assistant entity.

        Automatically converts kW to W and kWh to Wh based on unit_of_measurement.

        Args:
            entity_id: The entity ID (e.g., sensor.power_consumption).
            auto_convert: If True, automatically convert kW/kWh to W/Wh.

        Returns:
            The current state as a float (in base units if auto_convert), or None if unavailable.
        """
        if not entity_id:
            return None

        try:
            url = f"{self._base_url}/api/states/{entity_id}"
            response = self._client.get(url)
            response.raise_for_status()

            data = response.json()
            state = data.get("state")

            if state in ("unavailable", "unknown", None):
                logger.debug("Entity unavailable", entity_id=entity_id, state=state)
                return None

            self._connected = True
            self._last_error = None

            value = float(state)

            # Auto-convert based on unit_of_measurement
            if auto_convert:
                attributes = data.get("attributes", {})
                unit = attributes.get("unit_of_measurement", "")
                if unit in UNIT_CONVERSIONS:
                    value = value * UNIT_CONVERSIONS[unit]
                    logger.debug(
                        "Converted value",
                        entity_id=entity_id,
                        original_unit=unit,
                        conversion_factor=UNIT_CONVERSIONS[unit],
                    )

            return value

        except httpx.HTTPStatusError as e:
            self._last_error = f"HTTP error: {e.response.status_code}"
            logger.error(
                "HTTP error fetching entity",
                entity_id=entity_id,
                status_code=e.response.status_code,
            )
            return None

        except httpx.RequestError as e:
            self._connected = False
            self._last_error = f"Request error: {e}"
            logger.error(
                "Request error fetching entity", entity_id=entity_id, error=str(e)
            )
            return None

        except ValueError as e:
            self._last_error = f"Value error: {e}"
            logger.error(
                "Could not parse entity state as float",
                entity_id=entity_id,
                error=str(e),
            )
            return None

    def get_entity_with_unit(self, entity_id: str) -> EntityValue:
        """Get entity value with unit information.

        Args:
            entity_id: The entity ID.

        Returns:
            EntityValue with raw value, unit, and converted value.
        """
        if not entity_id:
            return EntityValue(None, None, None)

        try:
            url = f"{self._base_url}/api/states/{entity_id}"
            response = self._client.get(url)
            response.raise_for_status()

            data = response.json()
            state = data.get("state")

            if state in ("unavailable", "unknown", None):
                return EntityValue(None, None, None)

            self._connected = True
            value = float(state)
            attributes = data.get("attributes", {})
            unit = attributes.get("unit_of_measurement")
            last_updated = data.get("last_updated")

            # Calculate converted value
            converted = value
            if unit in UNIT_CONVERSIONS:
                converted = value * UNIT_CONVERSIONS[unit]

            return EntityValue(value, unit, converted, last_updated)

        except Exception as e:
            logger.debug(
                "Error getting entity with unit", entity_id=entity_id, error=str(e)
            )
            return EntityValue(None, None, None)

    def is_connected(self) -> bool:
        """Check if connected to Home Assistant.

        Returns:
            True if the last request was successful.
        """
        return self._connected

    def test_connection(self) -> bool:
        """Test the connection to Home Assistant.

        Returns:
            True if connection is successful.
        """
        try:
            url = f"{self._base_url}/api/"
            response = self._client.get(url)
            response.raise_for_status()

            data = response.json()
            if "message" in data:
                logger.info("Connected to Home Assistant", message=data["message"])
                self._connected = True
                return True

            return False

        except Exception as e:
            logger.error("Connection test failed", error=str(e))
            self._connected = False
            return False

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    @property
    def last_error(self) -> Optional[str]:
        """Get the last error message."""
        return self._last_error
