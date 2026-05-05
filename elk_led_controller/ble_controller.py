from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Callable, Coroutine, Optional

from bleak import BleakClient, BleakScanner

from .protocol import DeviceInfo


SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_UUID_DEFAULT = "0000fff3-0000-1000-8000-00805f9b34fb"
NAME_SUBSTR = "ELK-BLEDOM"


@dataclass
class ConnectionState:
    connected: bool = False
    device: DeviceInfo | None = None
    last_error: str | None = None


class BleController:
    def __init__(
        self,
        on_state: Callable[[ConnectionState], None] | None = None,
        on_last_command: Callable[[str], None] | None = None,
    ) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()

        self._client: BleakClient | None = None
        self._write_uuid = WRITE_UUID_DEFAULT
        self._state = ConnectionState()

        self._on_state = on_state
        self._on_last_command = on_last_command

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="ble-loop", daemon=True)
        self._thread.start()
        self._loop_ready.wait(timeout=5)
        if not self._loop:
            raise RuntimeError("BLE event loop failed to start")

    def stop(self) -> None:
        if not self._loop:
            return
        fut = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        try:
            fut.result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    def submit(self, coro: Coroutine) -> "asyncio.Future":
        if not self._loop:
            raise RuntimeError("BLE loop not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def is_connected(self) -> bool:
        return bool(self._state.connected)

    def set_write_uuid(self, uuid: str) -> None:
        self._write_uuid = uuid

    async def scan(self, timeout: float = 5.0) -> list[DeviceInfo]:
        devices = await BleakScanner.discover(timeout=timeout)
        found: list[DeviceInfo] = []
        for d in devices:
            name = (d.name or "").strip()
            if NAME_SUBSTR.lower() in name.lower():
                found.append(DeviceInfo(address=d.address, name=name, rssi=getattr(d, "rssi", None)))
        found.sort(key=lambda x: (x.rssi is None, -(x.rssi or -999)))
        return found

    async def connect(self, address: str, name: str = "", write_uuid: Optional[str] = None) -> None:
        await self.disconnect()
        self._write_uuid = write_uuid or self._write_uuid
        self._state.last_error = None
        self._emit_state(connected=False, device=DeviceInfo(address=address, name=name or address))

        client = BleakClient(address)
        try:
            await client.connect()
            client.set_disconnected_callback(self._on_disconnected)
            self._client = client
            self._emit_state(connected=True, device=DeviceInfo(address=address, name=name or address))
        except Exception as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            self._client = None
            self._emit_state(connected=False, device=None, last_error=str(e))
            raise

    async def disconnect(self) -> None:
        if not self._client:
            self._emit_state(connected=False)
            return
        client = self._client
        self._client = None
        try:
            await client.disconnect()
        finally:
            self._emit_state(connected=False)

    async def write(self, data: bytes, label: str = "") -> None:
        if not self._client:
            raise RuntimeError("Not connected")
        await self._client.write_gatt_char(self._write_uuid, data, response=False)
        if self._on_last_command:
            self._on_last_command(label or data.hex(" "))

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._loop_ready.set()
        loop.run_forever()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

    async def _shutdown(self) -> None:
        try:
            await self.disconnect()
        except Exception:
            pass

    def _on_disconnected(self, _client: BleakClient) -> None:
        self._emit_state(connected=False, last_error="Disconnected")

    def _emit_state(
        self,
        *,
        connected: Optional[bool] = None,
        device: DeviceInfo | None | object = object(),
        last_error: str | None | object = object(),
    ) -> None:
        if connected is not None:
            self._state.connected = connected
        if device is not object():
            self._state.device = None if device is None else device  # type: ignore[assignment]
        if last_error is not object():
            self._state.last_error = None if last_error is None else last_error  # type: ignore[assignment]
        if self._on_state:
            self._on_state(self._state)

