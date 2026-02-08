"""Tests for the HTTP server module."""

import time
from unittest.mock import MagicMock, AsyncMock, patch
import socket

import pytest
from fastapi.testclient import TestClient

from src.servers.http_server import (
    HTTPServer,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcError,
)
from src.emulator import MeterData


def get_free_port():
    """Dynamically get an available port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

class TestJsonRpcModels:
    """Tests for JSON-RPC Pydantic models."""


    def test_json_rpc_request_defaults(self):
        """Test JsonRpcRequest default values."""
        req = JsonRpcRequest(method="test")
        assert req.jsonrpc == "2.0"
        assert req.method == "test"
        assert req.params is None
        assert req.id is None

    def test_json_rpc_request_with_values(self):
        """Test JsonRpcRequest with all values."""
        req = JsonRpcRequest(
            method="EM.GetStatus",
            params={"id": 0},
            id=123,
        )
        assert req.method == "EM.GetStatus"
        assert req.params == {"id": 0}
        assert req.id == 123

    def test_json_rpc_response_with_result(self):
        """Test JsonRpcResponse with result."""
        resp = JsonRpcResponse(result={"key": "value"}, id=1)
        assert resp.result == {"key": "value"}
        assert resp.error is None

    def test_json_rpc_response_with_error(self):
        """Test JsonRpcResponse with error."""
        resp = JsonRpcResponse(
            error={"code": -32601, "message": "Method not found"},
            id=1,
        )
        assert resp.result is None
        assert resp.error["code"] == -32601

    def test_json_rpc_error(self):
        """Test JsonRpcError model."""
        err = JsonRpcError(code=-32700, message="Parse error")
        assert err.code == -32700
        assert err.message == "Parse error"
        assert err.data is None


class TestHTTPServer:
    """Tests for the HTTPServer class."""

    @pytest.fixture
    def mock_data_manager(self, sample_meter_data):
        """Create a mock data manager."""
        manager = MagicMock()
        manager.get_data.return_value = sample_meter_data
        return manager

    @pytest.fixture
    def http_server(self, shelly_device, mock_data_manager):
        """Create an HTTPServer for testing."""
        return HTTPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="127.0.0.1",
            port=18080,
        )

    @pytest.fixture
    def client(self, http_server):
        """Create a TestClient for the HTTP server."""
        return TestClient(http_server.app_instance)

    def test_init(self, shelly_device, mock_data_manager):
        """Test HTTPServer initialization."""
        server = HTTPServer(
            device=shelly_device,
            data_manager=mock_data_manager,
            host="0.0.0.0",
            port=80,
        )
        assert server.host == "0.0.0.0"
        assert server.port == 80
        assert server.device is shelly_device
        assert server.app_instance is not None

    def test_get_device_info(self, http_server):
        """Test _get_device_info method."""
        info = http_server._get_device_info()

        assert info["id"] == http_server.device.device_id
        assert info["gen"] == 2
        assert info["model"] == "SPEM-003CEBEU"
        assert info["auth_en"] is False

    def test_get_em_status(self, http_server, sample_meter_data):
        """Test _get_em_status method."""
        status = http_server._get_em_status(0)

        assert status["id"] == 0
        assert "a_current" in status
        assert "a_voltage" in status
        assert "total_act_power" in status

    def test_get_em_status_invalid_data(self, http_server, mock_data_manager):
        """Test _get_em_status with invalid data returns zeros with error flag."""
        invalid_data = MeterData(is_valid=False)
        mock_data_manager.get_data.return_value = invalid_data

        status = http_server._get_em_status(0)

        assert status["id"] == 0
        assert status["total_act_power"] == 0.0
        assert "power_meter_failure" in status["errors"]

    def test_get_emdata_status(self, http_server):
        """Test _get_emdata_status method."""
        status = http_server._get_emdata_status(0)

        assert status["id"] == 0
        assert "total_act" in status
        assert "total_act_ret" in status

    def test_get_emdata_status_invalid_data(self, http_server, mock_data_manager):
        """Test _get_emdata_status with invalid data returns zeros."""
        invalid_data = MeterData(is_valid=False)
        mock_data_manager.get_data.return_value = invalid_data

        status = http_server._get_emdata_status(0)

        assert status["id"] == 0
        assert status["total_act"] == 0.0

    def test_get_sys_status(self, http_server):
        """Test _get_sys_status method."""
        status = http_server._get_sys_status()

        assert "mac" in status
        assert "unixtime" in status
        assert "uptime" in status
        assert status["restart_required"] is False

    def test_get_wifi_status(self, http_server):
        """Test _get_wifi_status method."""
        status = http_server._get_wifi_status()

        assert status["status"] == "got ip"
        assert "rssi" in status

    def test_get_wifi_status_with_0000_host(self, shelly_device, mock_data_manager):
        """Test _get_wifi_status with 0.0.0.0 host."""
        server = HTTPServer(shelly_device, mock_data_manager, "0.0.0.0", 80)
        status = server._get_wifi_status()

        assert status["sta_ip"] == "192.168.1.100"

    def test_get_full_status(self, http_server):
        """Test _get_full_status method."""
        status = http_server._get_full_status()

        assert "sys" in status
        assert "wifi" in status
        assert "em:0" in status
        assert "emdata:0" in status

    def test_get_em_config(self, http_server):
        """Test _get_em_config method."""
        config = http_server._get_em_config(0)

        assert config["id"] == 0
        assert config["ct_type"] == "120A"

    def test_get_full_config(self, http_server):
        """Test _get_full_config method."""
        config = http_server._get_full_config()

        assert "sys" in config
        assert "wifi" in config
        assert "em:0" in config

    def test_compare_status_dicts_changed(self, http_server):
        """Test _compare_status_dicts with changed status."""
        old = {"em:0": {"a_act_power": 100}}
        new = {"em:0": {"a_act_power": 200}}

        assert http_server._compare_status_dicts(old, new) is True

    def test_compare_status_dicts_unchanged(self, http_server):
        """Test _compare_status_dicts with unchanged status."""
        old = {"em:0": {"a_act_power": 100}}
        new = {"em:0": {"a_act_power": 100}}

        assert http_server._compare_status_dicts(old, new) is False

    def test_compare_status_dicts_ignores_time(self, http_server):
        """Test _compare_status_dicts ignores time fields."""
        old = {"sys": {"time": "10:00", "unixtime": 1000, "uptime": 100}}
        new = {"sys": {"time": "10:01", "unixtime": 1001, "uptime": 101}}

        # Should be considered unchanged (time fields ignored)
        assert http_server._compare_status_dicts(old, new) is False

    def test_compare_status_dicts_empty(self, http_server):
        """Test _compare_status_dicts with empty dict."""
        assert http_server._compare_status_dicts({}, {"key": "value"}) is True
        assert http_server._compare_status_dicts(None, {"key": "value"}) is True

    def test_device_id_from_device(self, http_server):
        """Test device_id comes from ShellyDevice."""
        assert http_server.device.device_id == "test-emulator"

    def test_build_notify_status_partial(self, http_server):
        """Test _build_notify_status for partial status."""
        notification = http_server._build_notify_status(full=False, dst="client_1")

        assert notification["method"] == "NotifyStatus"
        assert notification["dst"] == "client_1"
        assert "em:0" in notification["params"]

    def test_build_notify_status_full(self, http_server):
        """Test _build_notify_status for full status."""
        notification = http_server._build_notify_status(full=True)

        assert notification["method"] == "NotifyFullStatus"
        assert "sys" in notification["params"]
        assert "wifi" in notification["params"]

    # HTTP endpoint tests

    def test_endpoint_shelly(self, client):
        """Test GET /shelly endpoint."""
        response = client.get("/shelly")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["gen"] == 2

    def test_endpoint_rpc_post(self, client):
        """Test POST /rpc endpoint."""
        response = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "method": "Shelly.GetDeviceInfo", "id": 1},
        )
        assert response.status_code == 200

    def test_endpoint_rpc_get_device_info(self, client):
        """Test GET /rpc/Shelly.GetDeviceInfo endpoint."""
        response = client.get("/rpc/Shelly.GetDeviceInfo")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data

    def test_endpoint_rpc_get_status(self, client):
        """Test GET /rpc/Shelly.GetStatus endpoint."""
        response = client.get("/rpc/Shelly.GetStatus")
        assert response.status_code == 200
        data = response.json()
        assert "sys" in data

    def test_endpoint_rpc_get_config(self, client):
        """Test GET /rpc/Shelly.GetConfig endpoint."""
        response = client.get("/rpc/Shelly.GetConfig")
        assert response.status_code == 200
        data = response.json()
        assert "sys" in data

    def test_endpoint_rpc_em_get_status(self, client):
        """Test GET /rpc/EM.GetStatus endpoint."""
        response = client.get("/rpc/EM.GetStatus?id=0")
        assert response.status_code == 200
        data = response.json()
        assert "a_current" in data

    def test_endpoint_rpc_em_get_config(self, client):
        """Test GET /rpc/EM.GetConfig endpoint."""
        response = client.get("/rpc/EM.GetConfig?id=0")
        assert response.status_code == 200

    def test_endpoint_rpc_emdata_get_status(self, client):
        """Test GET /rpc/EMData.GetStatus endpoint."""
        response = client.get("/rpc/EMData.GetStatus?id=0")
        assert response.status_code == 200

    def test_endpoint_rpc_list_methods(self, client):
        """Test GET /rpc/Shelly.ListMethods endpoint."""
        response = client.get("/rpc/Shelly.ListMethods")
        assert response.status_code == 200
        data = response.json()
        assert "methods" in data
        assert "Shelly.GetDeviceInfo" in data["methods"]


class TestHTTPServerRPC:
    """Tests for HTTP server RPC handling."""

    @pytest.fixture
    def http_server(self, shelly_device, sample_meter_data):
        """Create an HTTPServer for testing."""
        mock_dm = MagicMock()
        mock_dm.get_data.return_value = sample_meter_data
        return HTTPServer(shelly_device, mock_dm, "127.0.0.1", 18080)

    @pytest.mark.asyncio
    async def test_handle_rpc_list_methods(self, http_server):
        """Test _handle_rpc for Shelly.ListMethods."""
        response = await http_server._handle_rpc("Shelly.ListMethods", None, 1)
        assert "methods" in response.result

    @pytest.mark.asyncio
    async def test_handle_rpc_get_device_info(self, http_server):
        """Test _handle_rpc for Shelly.GetDeviceInfo."""
        response = await http_server._handle_rpc("Shelly.GetDeviceInfo", None, 1)
        assert "id" in response.result

    @pytest.mark.asyncio
    async def test_handle_rpc_get_status(self, http_server):
        """Test _handle_rpc for Shelly.GetStatus."""
        response = await http_server._handle_rpc("Shelly.GetStatus", None, 1)
        assert "sys" in response.result

    @pytest.mark.asyncio
    async def test_handle_rpc_get_config(self, http_server):
        """Test _handle_rpc for Shelly.GetConfig."""
        response = await http_server._handle_rpc("Shelly.GetConfig", None, 1)
        assert "sys" in response.result

    @pytest.mark.asyncio
    async def test_handle_rpc_em_get_status(self, http_server):
        """Test _handle_rpc for EM.GetStatus."""
        response = await http_server._handle_rpc("EM.GetStatus", {"id": 0}, 1)
        assert "a_current" in response.result

    @pytest.mark.asyncio
    async def test_handle_rpc_em_get_config(self, http_server):
        """Test _handle_rpc for EM.GetConfig."""
        response = await http_server._handle_rpc("EM.GetConfig", {"id": 0}, 1)
        assert response.result["id"] == 0

    @pytest.mark.asyncio
    async def test_handle_rpc_emdata_get_status(self, http_server):
        """Test _handle_rpc for EMData.GetStatus."""
        response = await http_server._handle_rpc("EMData.GetStatus", {"id": 0}, 1)
        assert "total_act" in response.result

    @pytest.mark.asyncio
    async def test_handle_rpc_method_not_found(self, http_server):
        """Test _handle_rpc for unknown method."""
        response = await http_server._handle_rpc("Unknown.Method", None, 1)
        assert response.error is not None
        assert response.error["code"] == -32601

    @pytest.mark.asyncio
    async def test_handle_rpc_exception(self, http_server):
        """Test _handle_rpc with exception."""
        # Force an exception by mocking
        with patch.object(
            http_server, "_get_device_info", side_effect=Exception("Test error")
        ):
            response = await http_server._handle_rpc("Shelly.GetDeviceInfo", None, 1)
            assert response.error is not None
            assert response.error["code"] == -32000


class TestHTTPServerStartStop:
    """Tests for HTTP server start/stop."""

    @pytest.fixture
    def http_server(self, shelly_device, sample_meter_data):
        """Create an HTTPServer for testing."""
        mock_dm = MagicMock()
        mock_dm.get_data.return_value = sample_meter_data
        port = get_free_port() # Use a random free port
        return HTTPServer(shelly_device, mock_dm, "127.0.0.1", port)

    def test_start_stop(self, http_server):
        """Test starting and stopping the server."""
        http_server.start()
        assert http_server.server_thread is not None
        assert http_server.server_thread.is_alive()
        time.sleep(1) # Give server time to bind and start accepting connections

        http_server.stop()
        # Give server time to release port and thread to terminate
        time.sleep(2)
        assert http_server.server_thread is None or not http_server.server_thread.is_alive()

    def test_start_already_running(self, http_server):
        """Test starting when already running."""
        http_server.start()
        first_thread = http_server.server_thread
        assert first_thread is not None and first_thread.is_alive()
        time.sleep(1) # Give server time to bind and start accepting connections

        # Start again should be no-op (and not raise an error)
        http_server.start()
        # Assert that no new thread was created
        assert http_server.server_thread is first_thread
        assert http_server.server_thread.is_alive() # Still alive

        http_server.stop()
        # Give server time to release port and thread to terminate
        time.sleep(2)
        assert http_server.server_thread is None or not http_server.server_thread.is_alive()

    def test_stop_not_running(self, http_server):
        """Test stopping when not running."""
        # Should not raise
        http_server.stop()


class TestHTTPServerWebSocket:
    """Tests for HTTP server WebSocket functionality."""

    @pytest.fixture
    def http_server(self, shelly_device, sample_meter_data):
        """Create an HTTPServer for testing."""
        mock_dm = MagicMock()
        mock_dm.get_data.return_value = sample_meter_data
        return HTTPServer(shelly_device, mock_dm, "127.0.0.1", 18080)

    @pytest.mark.asyncio
    async def test_send_status_update_no_clients(self, http_server):
        """Test _send_status_update with no clients."""
        # Should not raise
        await http_server._send_status_update()

    @pytest.mark.asyncio
    async def test_send_status_update_always_sends(self, http_server):
        """Test _send_status_update always sends to connected clients."""
        mock_ws = AsyncMock()
        http_server.websocket_clients[mock_ws] = "user_1"

        await http_server._send_status_update()

        # Always sends regardless of status change
        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_status_update_with_change(self, http_server):
        """Test _send_status_update sends to connected clients."""
        mock_ws = AsyncMock()
        http_server.websocket_clients[mock_ws] = "user_1"

        await http_server._send_status_update()

        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_status_update_client_disconnected(self, http_server):
        """Test _send_status_update when client disconnects."""
        from fastapi import WebSocketDisconnect

        mock_ws = AsyncMock()
        mock_ws.send_text.side_effect = WebSocketDisconnect()
        http_server.websocket_clients[mock_ws] = "user_1"

        await http_server._send_status_update()

        # Client should be removed
        assert mock_ws not in http_server.websocket_clients

    @pytest.mark.asyncio
    async def test_send_status_update_client_error(self, http_server):
        """Test _send_status_update with client error."""
        mock_ws = AsyncMock()
        mock_ws.send_text.side_effect = Exception("Connection error")
        http_server.websocket_clients[mock_ws] = "user_1"

        await http_server._send_status_update()

        # Client should be removed
        assert mock_ws not in http_server.websocket_clients

    @pytest.mark.asyncio
    async def test_start_stop_push_task(self, http_server):
        """Test starting and stopping the push task."""
        await http_server._start_push_task()
        assert http_server._push_task is not None

        await http_server._stop_push_task()
        assert http_server._push_task is None

    @pytest.mark.asyncio
    async def test_stop_push_task_not_started(self, http_server):
        """Test stopping push task when not started."""
        http_server._push_task = None
        await http_server._stop_push_task()
        assert http_server._push_task is None

    @pytest.mark.asyncio
    async def test_run_push_task_cancelled(self, http_server):
        """Test push task cancellation."""
        http_server._push_task_stop_event.set()
        # Should complete without error
        await http_server._run_push_task()

    @pytest.mark.asyncio
    async def test_run_push_task_exception(self, http_server):
        """Test push task handles exceptions."""
        http_server._push_task_stop_event.clear()

        call_count = [0]

        async def failing_send():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Test error")
            http_server._push_task_stop_event.set()

        http_server._send_status_update = failing_send

        # Should handle exception
        await http_server._run_push_task()
