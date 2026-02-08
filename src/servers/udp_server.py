"""UDP JSON-RPC server for Shelly Pro 3EM emulation."""

import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from ..config import get_logger
from ..emulator.data_manager import DataManager, build_em_status
from ..emulator.shelly_device import ShellyDevice

logger = get_logger(__name__)


class UDPServer:
    """UDP server for Shelly JSON-RPC protocol.

    Handles EM.GetStatus and EM1.GetStatus requests from Marstek devices.
    """

    def __init__(
        self,
        device: ShellyDevice,
        data_manager: DataManager,
        host: str = "0.0.0.0",
        ports: Optional[list[int]] = None,
    ):
        """Initialize the UDP server.

        Args:
            device: Shelly device configuration.
            data_manager: Data manager for meter data.
            host: Host address to bind to.
            ports: List of ports to listen on.
        """
        self._device = device
        self._data_manager = data_manager
        self._host = host
        self._ports = ports or [1010, 2220]

        self._sockets: list[socket.socket] = []
        self._threads: list[threading.Thread] = []
        self._executor = ThreadPoolExecutor(max_workers=10)
        self._running = False
        self._send_lock = threading.Lock()

    def start(self) -> None:
        """Start the UDP server on all configured ports."""
        if self._running:
            return

        self._running = True

        for port in self._ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((self._host, port))
                sock.settimeout(1.0)  # Allow periodic checking for stop
                self._sockets.append(sock)

                thread = threading.Thread(
                    target=self._listen_loop,
                    args=(sock, port),
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)

                logger.info("UDP server started", host=self._host, port=port)

            except OSError as e:
                logger.error("Failed to bind UDP port", port=port, error=str(e))

    def stop(self) -> None:
        """Stop the UDP server."""
        if not self._running:
            return

        self._running = False

        # Close all sockets
        for sock in self._sockets:
            try:
                sock.close()
            except Exception:
                pass

        # Wait for threads to finish
        for thread in self._threads:
            thread.join(timeout=2.0)

        self._executor.shutdown(wait=False)
        self._sockets.clear()
        self._threads.clear()

        logger.info("UDP server stopped")

    def _listen_loop(self, sock: socket.socket, port: int) -> None:
        """Listen for incoming UDP messages.

        Args:
            sock: Socket to listen on.
            port: Port number (for logging).
        """
        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                # If data is empty during shutdown, exit cleanly
                if not data and not self._running:
                    break
                if not self._running:  # Check again in case of race condition before processing
                    break
                self._executor.submit(self._handle_request, sock, data, addr, port)
            except socket.timeout:
                continue
            except (OSError, socket.error, ValueError) as e: # Catch ValueError too
                if not self._running: # If stopping, just break silently
                    break
                # Otherwise, it's an unexpected error
                logger.error("Socket error in UDP listen loop", port=port, error=str(e))
                break # Break on unexpected errors to prevent busy-looping


    def _handle_request(
        self,
        sock: socket.socket,
        data: bytes,
        addr: tuple,
        port: int,
    ) -> None:
        """Handle an incoming UDP request.

        Args:
            sock: Socket to send response on.
            data: Request data.
            addr: Client address.
            port: Server port.
        """
        try:
            request_str = data.decode("utf-8")
            logger.info(
                "UDP request received",
                port=port,
                client=f"{addr[0]}:{addr[1]}",
                data=request_str[:200],
            )

            request = json.loads(request_str)
            response = self._process_request(request)

            if response:
                response_str = json.dumps(response, separators=(",", ":"))
                response_data = response_str.encode("utf-8")

                with self._send_lock:
                    sock.sendto(response_data, addr)

                logger.info(
                    "UDP response sent",
                    port=port,
                    client=f"{addr[0]}:{addr[1]}",
                    response=response_str[:200],
                )

        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON request", error=str(e))
        except Exception as e:
            logger.error("Error handling UDP request", error=str(e))

    def _process_request(self, request: dict) -> Optional[dict]:
        """Process a JSON-RPC request.

        Args:
            request: Parsed request dictionary.

        Returns:
            Response dictionary, or None if no response needed.
        """
        method = request.get("method", "")
        request_id = request.get("id", 0)
        params = request.get("params", {})

        # Check if this is a valid request for our device
        if not isinstance(params.get("id"), int):
            return None

        if method == "EM.GetStatus":
            return self._create_em_response(request_id)
        elif method == "EM1.GetStatus":
            return self._create_em1_response(request_id)
        elif method == "Shelly.GetDeviceInfo":
            return self._create_device_info_response(request_id)
        elif method == "EM.GetCTTypes":
            return self._create_ct_types_response(request_id)

        return None

    def _create_em_response(self, request_id: int) -> dict:
        """Create response for EM.GetStatus.

        Args:
            request_id: Request ID to echo back.

        Returns:
            Response dictionary with power values for all phases.
        """
        data = self._data_manager.get_data()
        result = build_em_status(data)

        # Apply decimal enforcer to power values (Marstek expects decimal points)
        result["a_act_power"] = self._format_power(data.phase_a.active_power)
        result["b_act_power"] = self._format_power(data.phase_b.active_power)
        result["c_act_power"] = self._format_power(data.phase_c.active_power)
        result["total_act_power"] = self._format_power(data.total_power)

        return {
            "id": request_id,
            "src": self._device.device_id,
            "dst": "unknown",
            "result": result,
        }

    def _create_em1_response(self, request_id: int) -> dict:
        """Create response for EM1.GetStatus (single-phase format).

        Args:
            request_id: Request ID to echo back.

        Returns:
            Response dictionary with total power value.
        """
        data = self._data_manager.get_data()
        total_power = self._format_power(data.total_power)

        return {
            "id": request_id,
            "src": self._device.device_id,
            "dst": "unknown",
            "result": {
                "id": 0,
                "act_power": total_power,
            },
        }

    def _create_device_info_response(self, request_id: int) -> dict:
        """Create response for Shelly.GetDeviceInfo.

        Args:
            request_id: Request ID to echo back.

        Returns:
            Response dictionary with device information.
        """
        return {
            "id": request_id,
            "src": self._device.device_id,
            "dst": "unknown",
            "result": self._device.get_device_info(),
        }

    def _create_ct_types_response(self, request_id: int) -> dict:
        """Create response for EM.GetCTTypes.

        Args:
            request_id: Request ID to echo back.

        Returns:
            Response dictionary with supported CT types.
        """
        return {
            "id": request_id,
            "src": self._device.device_id,
            "dst": "unknown",
            "result": {
                "types": ["120A", "50A"]
            },
        }

    @staticmethod
    def _format_power(power: float) -> float:
        """Format power value with decimal enforcer.

        Marstek devices expect power values with decimal points.
        This adds a small offset if the value is a whole number.

        Args:
            power: Power value in watts.

        Returns:
            Formatted power value.
        """
        decimal_enforcer = 0.001

        if abs(power) < 0.1:
            # Preserve sign for small values
            return decimal_enforcer if power >= 0 else -decimal_enforcer

        result = round(power, 1)
        if result == round(result) or result == 0:
            # Add enforcer in the direction of the sign
            if result >= 0:
                result += decimal_enforcer
            else:
                result -= decimal_enforcer

        return result
