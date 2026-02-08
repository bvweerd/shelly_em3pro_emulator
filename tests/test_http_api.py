"""Tests for Shelly Gen2 HTTP API."""

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.config import (
    Settings,
    ShellyConfig,
    HTTPServerConfig,
    MDNSServerConfig,
    ServersConfig,
)
from src.emulator import ShellyDevice, DataManager, MeterData, PhaseData
from src.servers.http_server import HTTPServer


@pytest.fixture(scope="module")
def test_config():
    """Provides a test configuration for the emulator."""
    return Settings(
        shelly=ShellyConfig(
            device_id="test-shelly-emulator",
            device_name="Test Shelly",
            mac_address="00:11:22:33:44:55",
        ),
        servers=ServersConfig(
            http=HTTPServerConfig(enabled=True, host="127.0.0.1", port=8001),
            mdns=MDNSServerConfig(enabled=False),
            modbus=MagicMock(),
            udp=MagicMock(),
        ),
    )


@pytest.fixture(scope="module")
def http_test_client(test_config):
    """Provides a FastAPI TestClient for interacting with the HTTP server."""
    mock_data_manager = MagicMock(spec=DataManager)
    mock_data_manager.get_data.return_value = MeterData(
        phase_a=PhaseData(
            power=100.0,
            power_factor=0.9,
            current=0.5,
            voltage=230.0,
            energy_total=4000.0,
            energy_returned_total=10.0,
        ),
        phase_b=PhaseData(
            power=200.0,
            power_factor=0.95,
            current=1.0,
            voltage=231.0,
            energy_total=8000.0,
            energy_returned_total=20.0,
        ),
        phase_c=PhaseData(
            power=300.0,
            power_factor=0.8,
            current=1.5,
            voltage=229.0,
            energy_total=10000.0,
            energy_returned_total=30.0,
        ),
        total_energy=12345.67,
        total_energy_returned=123.45,
        timestamp=time.time(),
        is_valid=True,
    )

    mock_shelly_device = ShellyDevice(
        device_id=test_config.shelly.device_id,
        device_name=test_config.shelly.device_name,
        mac_address=test_config.shelly.mac_address,
    )
    mock_shelly_device.get_uptime = MagicMock(return_value=3600)
    mock_shelly_device.get_current_time = MagicMock(return_value=time.time())

    http_server_instance = HTTPServer(
        device=mock_shelly_device,
        data_manager=mock_data_manager,
        host=test_config.servers.http.host,
        port=test_config.servers.http.port,
    )

    with TestClient(http_server_instance.app_instance) as client:
        yield client


class TestShellyEndpoint:
    """Tests for /shelly endpoint (device identification)."""

    def test_returns_gen2_format(self, http_test_client, test_config):
        """Test /shelly returns Gen2 format."""
        response = http_test_client.get("/shelly")
        assert response.status_code == 200
        data = response.json()

        mac_no_colons = test_config.shelly.mac_address.replace(":", "").upper()
        assert data["mac"] == mac_no_colons
        assert data["name"] == test_config.shelly.device_name
        assert data["gen"] == 2
        assert data["model"] == "SPEM-003CEBEU"
        assert data["app"] == "Pro3EM"
        assert data["auth_en"] is False

    def test_device_id_format(self, http_test_client, test_config):
        """Test device ID matches the configured device_id."""
        response = http_test_client.get("/shelly")
        data = response.json()

        assert data["id"] == test_config.shelly.device_id


class TestRpcEndpoint:
    """Tests for /rpc JSON-RPC endpoint."""

    def test_list_methods(self, http_test_client):
        """Test Shelly.ListMethods."""
        response = http_test_client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "Shelly.ListMethods",
                "id": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "result" in data
        assert "methods" in data["result"]
        assert "Shelly.GetDeviceInfo" in data["result"]["methods"]
        assert "EM.GetStatus" in data["result"]["methods"]
        assert "EMData.GetStatus" in data["result"]["methods"]
        assert data["id"] == 1

    def test_get_device_info(self, http_test_client, test_config):
        """Test Shelly.GetDeviceInfo."""
        response = http_test_client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "Shelly.GetDeviceInfo",
                "id": 2,
            },
        )
        assert response.status_code == 200
        data = response.json()

        mac_no_colons = test_config.shelly.mac_address.replace(":", "").upper()
        assert data["result"]["mac"] == mac_no_colons
        assert data["result"]["gen"] == 2
        assert data["result"]["model"] == "SPEM-003CEBEU"
        assert data["id"] == 2

    def test_get_status(self, http_test_client, test_config):
        """Test Shelly.GetStatus returns Gen2 structure."""
        response = http_test_client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "Shelly.GetStatus",
                "id": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Gen2 structure
        assert "sys" in data["result"]
        assert "wifi" in data["result"]
        assert "em:0" in data["result"]
        assert "emdata:0" in data["result"]

        # Check sys
        mac_no_colons = test_config.shelly.mac_address.replace(":", "").upper()
        assert data["result"]["sys"]["mac"] == mac_no_colons
        assert data["result"]["sys"]["uptime"] == 3600

        # Check em:0
        assert data["result"]["em:0"]["total_act_power"] == 600.0
        assert data["result"]["em:0"]["a_act_power"] == 100.0

        assert data["id"] == 3

    def test_em_get_status(self, http_test_client):
        """Test EM.GetStatus."""
        response = http_test_client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "EM.GetStatus",
                "params": {"id": 0},
                "id": 4,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["result"]["id"] == 0
        assert data["result"]["total_act_power"] == 600.0
        assert data["result"]["a_act_power"] == 100.0
        assert data["result"]["b_act_power"] == 200.0
        assert data["result"]["c_act_power"] == 300.0
        assert data["result"]["a_voltage"] == 230.0
        assert data["id"] == 4

    def test_emdata_get_status(self, http_test_client):
        """Test EMData.GetStatus."""
        response = http_test_client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "EMData.GetStatus",
                "params": {"id": 0},
                "id": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["result"]["id"] == 0
        assert data["result"]["a_total_act_energy"] == 4000.0  # Wh
        assert data["result"]["total_act"] == 12345.67  # Wh
        assert data["id"] == 5

    def test_get_config(self, http_test_client, test_config):
        """Test Shelly.GetConfig."""
        response = http_test_client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "Shelly.GetConfig",
                "id": 6,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "sys" in data["result"]
        assert "wifi" in data["result"]
        assert "em:0" in data["result"]
        assert data["result"]["sys"]["device"]["name"] == test_config.shelly.device_name
        assert data["id"] == 6

    def test_method_not_found(self, http_test_client):
        """Test unknown method returns error."""
        response = http_test_client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "Unknown.Method",
                "id": 7,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "error" in data
        assert data["error"]["code"] == -32601
        assert data["error"]["message"] == "Method not found"
        assert data["id"] == 7


class TestHttpRpcShortcuts:
    """Tests for Gen2 HTTP RPC shortcuts (/rpc/MethodName)."""

    def test_get_device_info(self, http_test_client, test_config):
        """Test /rpc/Shelly.GetDeviceInfo."""
        response = http_test_client.get("/rpc/Shelly.GetDeviceInfo")
        assert response.status_code == 200
        data = response.json()

        mac_no_colons = test_config.shelly.mac_address.replace(":", "").upper()
        assert data["mac"] == mac_no_colons
        assert data["gen"] == 2

    def test_get_status(self, http_test_client):
        """Test /rpc/Shelly.GetStatus."""
        response = http_test_client.get("/rpc/Shelly.GetStatus")
        assert response.status_code == 200
        data = response.json()

        assert "sys" in data
        assert "em:0" in data
        assert data["em:0"]["total_act_power"] == 600.0

    def test_em_get_status(self, http_test_client):
        """Test /rpc/EM.GetStatus."""
        response = http_test_client.get("/rpc/EM.GetStatus")
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == 0
        assert data["total_act_power"] == 600.0
        # Check error fields
        assert "a_errors" in data
        assert "b_errors" in data
        assert "c_errors" in data
        assert "n_errors" in data
        assert "errors" in data
        assert isinstance(data["errors"], list)
        assert len(data["errors"]) == 0  # No errors in normal operation

    def test_em_get_status_with_id(self, http_test_client):
        """Test /rpc/EM.GetStatus with id parameter."""
        response = http_test_client.get("/rpc/EM.GetStatus?id=0")
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == 0

    def test_emdata_get_status(self, http_test_client):
        """Test /rpc/EMData.GetStatus."""
        response = http_test_client.get("/rpc/EMData.GetStatus")
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == 0
        assert "total_act" in data

    def test_list_methods(self, http_test_client):
        """Test /rpc/Shelly.ListMethods."""
        response = http_test_client.get("/rpc/Shelly.ListMethods")
        assert response.status_code == 200
        data = response.json()

        assert "methods" in data
        assert "EM.GetStatus" in data["methods"]
        assert "EM.GetCTTypes" in data["methods"]

    def test_em_get_ct_types(self, http_test_client):
        """Test /rpc/EM.GetCTTypes."""
        response = http_test_client.get("/rpc/EM.GetCTTypes")
        assert response.status_code == 200
        data = response.json()

        assert "types" in data
        assert "120A" in data["types"]
        assert "50A" in data["types"]
