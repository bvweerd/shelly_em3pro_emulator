"""Health check script for Docker container."""

import socket
import sys


def check_modbus(
    host: str = "127.0.0.1", port: int = 502, timeout: float = 5.0
) -> bool:
    """Check if Modbus TCP server is responding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_http(host: str = "127.0.0.1", port: int = 80, timeout: float = 5.0) -> bool:
    """Check if HTTP server is responding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def main() -> int:
    """Run health checks.

    Returns 0 if at least one server is healthy, 1 otherwise.
    """
    modbus_ok = check_modbus()
    http_ok = check_http()

    if modbus_ok or http_ok:
        return 0

    # If neither is responding, the container is unhealthy
    return 1


if __name__ == "__main__":
    sys.exit(main())
