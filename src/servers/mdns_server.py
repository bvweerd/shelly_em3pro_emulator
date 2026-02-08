import socket
import threading
from zeroconf import ServiceInfo, Zeroconf, IPVersion

from ..config import get_logger

logger = get_logger(__name__)


class MDNSServer(threading.Thread):
    def __init__(
        self,
        device_name: str,
        mac_address: str,
        http_port: int,
        host: str = "",
        model: str = "SPEM-003CEBEU",
        firmware_version: str = "1.1.0",
        fw_id: str = "20231219-133625/1.1.0-g9eb7ffd",
    ):
        super().__init__()
        self.device_name = device_name
        self.mac_address = mac_address.replace(":", "").upper()  # MAC without colons
        self.http_port = http_port
        self.host = host  # Optional: bind to specific IP
        self.model = model
        self.firmware_version = firmware_version
        self.fw_id = fw_id
        self.zeroconf = None
        self.service_info = None
        self.daemon = (
            True  # Allow main program to exit even if this thread is still running
        )

    def get_local_ip(self):
        """Attempts to get the local IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't actually connect, just tells OS to route traffic
            s.connect(("10.255.255.255", 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = "127.0.0.1"  # Fallback
        finally:
            s.close()
        return IP

    def run(self):
        # Use configured host if provided, otherwise auto-detect
        if self.host and self.host not in ("", "0.0.0.0"):
            ip_address = self.host
        else:
            ip_address = self.get_local_ip()

        # Create Zeroconf with specific interface to avoid VPN/virtual interface issues
        try:
            # Try to bind only to the specified IP's interface
            self.zeroconf = Zeroconf(
                interfaces=[ip_address],
                ip_version=IPVersion.V4Only,
            )
        except Exception as e:
            logger.warning(
                f"mDNS: Could not bind to specific interface, using all: {e}"
            )
            self.zeroconf = Zeroconf()

        logger.info(f"mDNS: Using IP address {ip_address} for advertisement.")

        # Device ID format: shellypro3em-XXXXXX (last 6 chars of MAC = last 3 bytes)
        device_id = f"shellypro3em-{self.mac_address[-6:].lower()}"

        # Properties for Shelly Gen2 device advertisement
        # These match what Home Assistant's Shelly integration expects
        properties = {
            "id": device_id,
            "mac": self.mac_address,
            "model": self.model,
            "gen": "2",  # Critical: Gen2 device
            "app": "Pro3EM",
            "ver": self.firmware_version,
            "fw_id": self.fw_id,
            "arch": "esp32",
            "auth_en": "false",
            "auth_domain": "",
            "discoverable": "true",
        }

        # Service name must start with "shelly" for Home Assistant discovery
        # Format: shellypro3em-XXXXXX (last 6 chars of MAC)
        shelly_service_name = (
            f"shellypro3em-{self.mac_address[-6:].lower()}._shelly._tcp.local."
        )

        # Server hostname for mDNS (the .local hostname that resolves to IP)
        server_hostname = f"shellypro3em-{self.mac_address[-6:].lower()}.local."

        self.service_info_shelly = ServiceInfo(
            "_shelly._tcp.local.",
            shelly_service_name,
            addresses=[socket.inet_aton(ip_address)],
            port=self.http_port,
            properties=properties,
            server=server_hostname,
        )

        # HTTP service name MUST start with "shelly*" for Home Assistant zeroconf discovery
        # Home Assistant manifest.json specifies: {"type": "_http._tcp.local.", "name": "shelly*"}
        http_service_name = (
            f"shellypro3em-{self.mac_address[-6:].lower()}._http._tcp.local."
        )
        self.service_info_http = ServiceInfo(
            "_http._tcp.local.",
            http_service_name,
            addresses=[socket.inet_aton(ip_address)],
            port=self.http_port,
            properties=properties,
            server=server_hostname,
        )

        logger.info(
            f"mDNS: Registering service {shelly_service_name} on port {self.http_port}"
        )
        logger.info(
            f"mDNS: Registering service {http_service_name} on port {self.http_port}"
        )
        try:
            self.zeroconf.register_service(self.service_info_shelly)
            self.zeroconf.register_service(self.service_info_http)
            logger.info("mDNS: Services registered successfully.")
        except Exception as e:
            logger.error(f"mDNS: Failed to register services: {e}")

    def stop(self):
        if self.zeroconf:
            logger.info("mDNS: Unregistering services and closing Zeroconf.")
            try:
                self.zeroconf.unregister_service(self.service_info_shelly)
                self.zeroconf.unregister_service(self.service_info_http)
                self.zeroconf.close()
                logger.info("mDNS: Services unregistered and Zeroconf closed.")
            except Exception as e:
                logger.error(f"mDNS: Error during unregistration/close: {e}")

