"""Shelly Gen2 HTTP API Server.

Implements the Shelly Gen2 HTTP API as documented at:
https://shelly-api-docs.shelly.cloud/gen2/
"""

import asyncio
import json
import threading
import time
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..config import get_logger
from ..emulator import DataManager, ShellyDevice
from ..emulator.data_manager import build_em_status

logger = get_logger(__name__)


# Pydantic models for JSON-RPC 2.0
class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[int] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[int] = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class HTTPServer:
    """Shelly Gen2 HTTP API Server with WebSocket support."""

    SHELLY_PUSH_INTERVAL = 1  # Seconds between checking for data to push

    def __init__(
        self, device: ShellyDevice, data_manager: DataManager, host: str, port: int
    ):
        self.device = device
        self.data_manager = data_manager
        self.host = host
        self.port = port
        self.app_instance = FastAPI(title="Shelly Pro 3EM Emulator")
        self.server_thread: Optional[threading.Thread] = None
        self.uvicorn_server = None
        # Map WebSocket -> client source ID for proper dst in notifications
        self.websocket_clients: Dict[WebSocket, str] = {}

        self._last_pushed_status: Optional[dict] = None
        self._push_task_stop_event = asyncio.Event()
        self._push_task: Optional[asyncio.Task] = None

        # New event for Uvicorn server shutdown
        self._server_stop_event = asyncio.Event()

        self._setup_websocket()  # WebSocket must be registered before HTTP routes
        self._setup_routes()

    def _get_device_info(self) -> dict:
        """Get device info in Gen2 format."""
        info = self.device.get_device_info()
        info["name"] = self.device.device_name
        info["slot"] = 0
        return info

    def _get_em_status(self, em_id: int = 0) -> dict:
        """Get EM component status (Gen2 EM.GetStatus)."""
        return build_em_status(self.data_manager.get_data(), em_id)

    def _get_emdata_status(self, em_id: int = 0) -> dict:
        """Get EMData component status (Gen2 EMData.GetStatus)."""
        meter_data = self.data_manager.get_data()
        no_data = not meter_data or not meter_data.is_valid or meter_data.is_stale

        return {
            "id": em_id,
            "a_total_act_energy": (
                round(meter_data.phase_a.energy_total, 2) if not no_data else 0.0
            ),
            "a_total_act_ret_energy": (
                round(meter_data.phase_a.energy_returned_total, 2)
                if not no_data
                else 0.0
            ),
            "b_total_act_energy": (
                round(meter_data.phase_b.energy_total, 2) if not no_data else 0.0
            ),
            "b_total_act_ret_energy": (
                round(meter_data.phase_b.energy_returned_total, 2)
                if not no_data
                else 0.0
            ),
            "c_total_act_energy": (
                round(meter_data.phase_c.energy_total, 2) if not no_data else 0.0
            ),
            "c_total_act_ret_energy": (
                round(meter_data.phase_c.energy_returned_total, 2)
                if not no_data
                else 0.0
            ),
            "total_act": round(meter_data.total_energy, 2) if not no_data else 0.0,
            "total_act_ret": (
                round(meter_data.total_energy_returned, 2) if not no_data else 0.0
            ),
        }

    def _get_sys_status(self) -> dict:
        """Get Sys component status."""
        return {
            "mac": self.device.mac_address,
            "restart_required": False,
            "time": time.strftime("%H:%M", time.localtime()),
            "unixtime": int(time.time()),
            "uptime": self.device.get_uptime(),
            "ram_size": 245388,
            "ram_free": 139388,
            "fs_size": 524288,
            "fs_free": 163840,
            "available_updates": {},
        }

    def _get_wifi_status(self) -> dict:
        """Get WiFi component status."""
        return {
            "sta_ip": self.host if self.host != "0.0.0.0" else "192.168.1.100",
            "status": "got ip",
            "ssid": "WiFi",
            "rssi": -55,
        }

    def _get_full_status(self) -> dict:
        """Get full device status (Gen2 Shelly.GetStatus)."""
        return {
            "sys": self._get_sys_status(),
            "wifi": self._get_wifi_status(),
            "em:0": self._get_em_status(0),
            "emdata:0": self._get_emdata_status(0),
        }

    def _get_em_config(self, em_id: int = 0) -> dict:
        """Get EM component config."""
        return {
            "id": em_id,
            "name": None,
            "blink_mode_selector": "active_energy",
            "phase_selector": "all",
            "monitor_phase_sequence": False,
            "ct_type": "120A",
            "reverse": {},
        }

    def _get_ct_types(self) -> dict:
        """Get supported current transformer types (Gen2 EM.GetCTTypes)."""
        return {"types": ["120A", "50A"]}

    def _get_full_config(self) -> dict:
        """Get full device config (Gen2 Shelly.GetConfig)."""
        return {
            "sys": {
                "device": {
                    "name": self.device.device_name,
                    "mac": self.device.mac_address,
                    "fw_id": self.device.fw_id,
                    "discoverable": True,
                },
            },
            "wifi": {
                "ap": {"enable": False},
                "sta": {"enable": True, "ssid": "WiFi"},
                "sta1": {"enable": False},
            },
            "em:0": self._get_em_config(0),
        }

    def _get_components(self, params: Optional[dict] = None) -> dict:
        """Get device components (Gen2 Shelly.GetComponents).

        This method returns the list of components on the device.
        For Pro 3EM this includes em:0 and emdata:0.

        Args:
            params: Optional parameters including offset, dynamic_only, include, keys.

        Returns:
            Dictionary with components, cfg_rev, offset, and total.
        """
        params = params or {}
        offset = params.get("offset", 0)
        dynamic_only = params.get("dynamic_only", False)
        include = params.get("include", [])
        keys_filter = params.get("keys")

        # Define static components for Pro 3EM
        all_components: list[dict[str, Any]] = [
            {"key": "em:0"},
            {"key": "emdata:0"},
        ]

        # Filter by dynamic_only (we have no dynamic components)
        if dynamic_only:
            components = []
        else:
            components = all_components

        # Filter by keys if provided
        if keys_filter:
            components = [c for c in components if c["key"] in keys_filter]

        # Add status/config if requested
        for comp in components:
            if "status" in include:
                if comp["key"] == "em:0":
                    comp["status"] = self._get_em_status(0)
                elif comp["key"] == "emdata:0":
                    comp["status"] = self._get_emdata_status(0)
            if "config" in include:
                if comp["key"] == "em:0":
                    comp["config"] = self._get_em_config(0)

        # Apply offset
        total = len(components)
        components = components[offset:]

        return {
            "components": components,
            "cfg_rev": 0,
            "offset": offset,
            "total": total,
        }

    def _compare_status_dicts(self, old_status: dict, new_status: dict) -> bool:
        """Compare two status dictionaries for significant changes.

        Ignores dynamic fields like 'time', 'unixtime', 'uptime'.
        """
        if not old_status or not new_status:
            return True

        # Fields to ignore for comparison (they change constantly)
        ignore_fields = ["time", "unixtime", "uptime"]

        def clean_status(status_dict):
            # Create a deep copy to avoid modifying original dictionaries
            cleaned = json.loads(json.dumps(status_dict))
            if "sys" in cleaned:
                for field in ignore_fields:
                    cleaned["sys"].pop(field, None)
            return cleaned

        cleaned_old = clean_status(old_status)
        cleaned_new = clean_status(new_status)

        return cleaned_old != cleaned_new

    def _build_notify_status(self, full: bool = False, dst: str = "user_1") -> dict:
        """Build a NotifyStatus or NotifyFullStatus notification.

        Args:
            full: If True, build NotifyFullStatus with all components.
                  If False, build NotifyStatus with changed components only.
            dst: Destination client ID for the notification.
        """
        device_id = self.device.device_id

        params: dict[str, Any] = {
            "ts": time.time(),
        }

        if full:
            # NotifyFullStatus includes all component statuses
            params["sys"] = self._get_sys_status()
            params["wifi"] = self._get_wifi_status()
            params["em:0"] = self._get_em_status(0)
            params["emdata:0"] = self._get_emdata_status(0)
        else:
            # NotifyStatus - include EM data (the frequently changing data)
            params["em:0"] = self._get_em_status(0)
            params["emdata:0"] = self._get_emdata_status(0)

        return {
            "src": device_id,
            "dst": dst,
            "method": "NotifyFullStatus" if full else "NotifyStatus",
            "params": params,
        }

    async def _send_status_update(self):
        """Send a NotifyStatus notification to all connected WebSocket clients."""
        if not self.websocket_clients:
            return

        # Send to all clients, track failed ones for removal
        clients_to_remove = []

        for client, client_src in list(self.websocket_clients.items()):
            notification = self._build_notify_status(full=False, dst=client_src)
            notification_json = json.dumps(notification)
            try:
                await asyncio.wait_for(client.send_text(notification_json), timeout=5.0)
                logger.debug(f"WebSocket NotifyStatus sent to {client.client}")
            except asyncio.TimeoutError:
                logger.warning(
                    f"WebSocket send timeout for {client.client}, removing zombie connection"
                )
                clients_to_remove.append(client)
            except WebSocketDisconnect:
                logger.info(
                    f"WebSocket client {client.client} disconnected during push."
                )
                clients_to_remove.append(client)
            except Exception as e:
                logger.warning(
                    f"Error sending WebSocket push notification to {client.client}: {e}"
                )
                clients_to_remove.append(client)

        # Remove disconnected clients
        for client in clients_to_remove:
            if client in self.websocket_clients:
                del self.websocket_clients[client]

    async def _run_push_task(self):
        """Background task to periodically push status updates to WebSocket clients."""
        logger.info("WebSocket push task started.")
        while not self._push_task_stop_event.is_set():
            try:
                await asyncio.sleep(self.SHELLY_PUSH_INTERVAL)
                await self._send_status_update()
            except asyncio.CancelledError:
                logger.info("WebSocket push task cancelled.")
                break
            except Exception as e:
                logger.exception(f"WebSocket push task error: {e}")
                # Continue loop - don't let a single error stop all future pushes
        logger.info("WebSocket push task stopped.")

    async def _start_push_task(self):
        """Start the WebSocket push background task."""
        self._push_task_stop_event.clear()
        self._push_task = asyncio.create_task(self._run_push_task())

    async def _stop_push_task(self):
        """Stop the WebSocket push background task."""
        if self._push_task:
            self._push_task_stop_event.set()
            await self._push_task  # Wait for the task to finish its current loop iteration and stop
            self._push_task = None

    def _setup_routes(self):
        """Setup HTTP routes for Gen2 API."""
        self.app_instance.add_event_handler("startup", self._start_push_task)
        self.app_instance.add_event_handler("shutdown", self._stop_push_task)

        # Gen2 /shelly endpoint - device identification
        @self.app_instance.get("/shelly")
        async def get_shelly():
            """Device identification endpoint (equivalent to Shelly.GetDeviceInfo)."""
            return self._get_device_info()

        # Gen2 JSON-RPC endpoint
        @self.app_instance.post("/rpc")
        async def rpc_post(request: JsonRpcRequest):
            """JSON-RPC 2.0 endpoint for all RPC methods."""
            return await self._handle_rpc(request.method, request.params, request.id)

        # Gen2 HTTP RPC shortcuts: /rpc/MethodName
        @self.app_instance.get("/rpc/Shelly.GetDeviceInfo")
        async def rpc_get_device_info():
            return self._get_device_info()

        @self.app_instance.get("/rpc/Shelly.GetStatus")
        async def rpc_get_status():
            return self._get_full_status()

        @self.app_instance.get("/rpc/Shelly.GetConfig")
        async def rpc_get_config():
            return self._get_full_config()

        @self.app_instance.get("/rpc/EM.GetStatus")
        async def rpc_em_get_status(id: int = 0):
            return self._get_em_status(id)

        @self.app_instance.get("/rpc/EM.GetConfig")
        async def rpc_em_get_config(id: int = 0):
            return self._get_em_config(id)

        @self.app_instance.get("/rpc/EMData.GetStatus")
        async def rpc_emdata_get_status(id: int = 0):
            return self._get_emdata_status(id)

        @self.app_instance.get("/rpc/Shelly.ListMethods")
        async def rpc_list_methods():
            return {
                "methods": [
                    "Shelly.ListMethods",
                    "Shelly.GetDeviceInfo",
                    "Shelly.GetStatus",
                    "Shelly.GetConfig",
                    "EM.GetStatus",
                    "EM.GetConfig",
                    "EM.GetCTTypes",
                    "EMData.GetStatus",
                ]
            }

        @self.app_instance.get("/rpc/EM.GetCTTypes")
        async def rpc_em_get_ct_types():
            return self._get_ct_types()

    def _setup_websocket(self):
        """Setup WebSocket endpoint for Gen2 RPC."""

        @self.app_instance.websocket("/rpc")
        async def websocket_rpc(websocket: WebSocket):
            """WebSocket endpoint for JSON-RPC communication (required by Home Assistant)."""
            await websocket.accept()
            # Default client source until we receive their first message with src
            client_src = "user_1"
            self.websocket_clients[websocket] = client_src
            logger.info(
                f"WebSocket client connected from {websocket.client} - total clients: {len(self.websocket_clients)}"
            )

            # Send NotifyFullStatus immediately upon connection
            # This is required by Home Assistant Shelly integration
            try:
                initial_status = self._build_notify_status(full=True, dst=client_src)
                initial_status_json = json.dumps(initial_status)
                logger.debug(
                    f"Sending NotifyFullStatus to new client: {initial_status_json[:200]}..."
                )
                await websocket.send_text(initial_status_json)
                logger.debug(f"Sent NotifyFullStatus to new client {websocket.client}")
            except Exception as e:
                logger.warning(
                    f"Failed to send initial status to {websocket.client}: {e}"
                )

            try:
                while True:
                    # Receive RPC request
                    data = await websocket.receive_text()
                    logger.info(f"WebSocket received: {data[:200]}")

                    try:
                        request = json.loads(data)
                        method = request.get("method", "")
                        params = request.get("params")
                        request_id = request.get("id")
                        # Track client's src for use in dst field of responses/notifications
                        if "src" in request:
                            client_src = request["src"]
                            self.websocket_clients[websocket] = client_src

                        # Handle the RPC request
                        rpc_response = await self._handle_rpc(
                            method, params, request_id
                        )

                        # Build Shelly-format response (not JSON-RPC format)
                        # aioshelly expects: {"id": N, "src": "device", "dst": "client", "result": {...}}
                        response = {
                            "id": request_id,
                            "src": self.device.device_id,
                            "dst": client_src,
                        }
                        if rpc_response.error:
                            response["error"] = rpc_response.error
                        else:
                            response["result"] = rpc_response.result

                        response_json = json.dumps(response)
                        await websocket.send_text(response_json)
                        logger.debug(f"WebSocket sent: {response_json}")

                    except json.JSONDecodeError:
                        error_response = {
                            "id": None,
                            "src": self.device.device_id,
                            "error": {"code": -32700, "message": "Parse error"},
                        }
                        await websocket.send_text(json.dumps(error_response))

            except WebSocketDisconnect:
                logger.info(f"WebSocket client disconnected from {websocket.client}")
            except Exception as e:
                logger.exception(f"WebSocket error: {e}")
            finally:
                if websocket in self.websocket_clients:
                    del self.websocket_clients[websocket]
                    logger.info(
                        f"WebSocket client removed, remaining: {len(self.websocket_clients)}"
                    )

    async def _handle_rpc(
        self, method: str, params: Optional[dict], request_id: Optional[int]
    ) -> JsonRpcResponse:
        """Handle JSON-RPC request."""
        try:
            em_id = params.get("id", 0) if params else 0

            if method == "Shelly.ListMethods":
                result: dict[str, Any] = {
                    "methods": [
                        "Shelly.ListMethods",
                        "Shelly.GetDeviceInfo",
                        "Shelly.GetStatus",
                        "Shelly.GetConfig",
                        "Shelly.GetComponents",
                        "EM.GetStatus",
                        "EM.GetConfig",
                        "EM.GetCTTypes",
                        "EMData.GetStatus",
                        "Script.List",
                        "Script.GetCode",
                    ]
                }
            elif method == "Shelly.GetDeviceInfo":
                result = self._get_device_info()
            elif method == "Shelly.GetStatus":
                result = self._get_full_status()
            elif method == "Shelly.GetConfig":
                result = self._get_full_config()
            elif method == "EM.GetStatus":
                result = self._get_em_status(em_id)
            elif method == "EM.GetConfig":
                result = self._get_em_config(em_id)
            elif method == "EM.GetCTTypes":
                result = self._get_ct_types()
            elif method == "EMData.GetStatus":
                result = self._get_emdata_status(em_id)
            elif method == "Shelly.GetComponents":
                result = self._get_components(params)
            elif method == "Script.GetCode":
                # Pro 3EM doesn't support scripts, return empty
                result = {"data": ""}
            elif method == "Script.List":
                # Pro 3EM doesn't support scripts
                result = {"scripts": []}
            else:
                return JsonRpcResponse(
                    error={"code": -32601, "message": "Method not found"},
                    id=request_id,
                )

            return JsonRpcResponse(result=result, id=request_id)

        except Exception as e:
            logger.exception(f"RPC method {method} failed")
            return JsonRpcResponse(
                error={"code": -32000, "message": f"Internal error: {e}"},
                id=request_id,
            )

    def start(self):
        """Start the HTTP server."""
        if self.server_thread and self.server_thread.is_alive():
            logger.info("HTTP server is already running.")
            return

        config = uvicorn.Config(
            self.app_instance,
            host=self.host,
            port=self.port,
            log_level="warning",
        )

        class ThreadedServer(uvicorn.Server):
            def install_signal_handlers(self):
                pass  # Handled by the main process

        self.uvicorn_server = ThreadedServer(config=config)

        def run_server_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def serve_with_shutdown():
                await self.uvicorn_server.serve()
                await self._server_stop_event.wait()
                self.uvicorn_server.should_exit = True

            try:
                loop.run_until_complete(serve_with_shutdown())
            finally:
                loop.close()
                self._server_stop_event.clear()  # Clear the event for next start

        self._server_stop_event.clear()  # Ensure event is clear before starting
        self.server_thread = threading.Thread(target=run_server_in_thread, daemon=True)
        self.server_thread.start()
        logger.info(f"HTTP server started on http://{self.host}:{self.port}")

    def stop(self):
        """Stop the HTTP server."""
        if self.server_thread and self.server_thread.is_alive():
            logger.info("Stopping HTTP server")
            self._server_stop_event.set()  # Signal the server thread to stop
            self.server_thread.join(timeout=10)  # Wait for thread to finish
            if self.server_thread.is_alive():
                logger.warning("HTTP server thread did not terminate gracefully.")
            self.server_thread = None
            self.uvicorn_server = None
        logger.info("HTTP server stopped.")
