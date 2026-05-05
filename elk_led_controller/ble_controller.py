from __future__ import annotations

import asyncio
import contextlib
import threading
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional

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
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()

        self._client: BleakClient | None = None
        self._write_uuid = WRITE_UUID_DEFAULT
        self._state = ConnectionState()

        self._on_state = on_state
        self._on_last_command = on_last_command
        self._on_log = on_log

        self._queue: asyncio.Queue[tuple[bytes, str]] | None = None
        self._worker_task: asyncio.Task | None = None
        self._write_delay_s: float = 0.05
        self._stopping = False

        self._last_device: dict[str, str] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="ble-loop", daemon=True)
        self._thread.start()
        self._loop_ready.wait(timeout=5)
        if not self._loop:
            raise RuntimeError("BLE event loop failed to start")
        self.submit(self._ensure_worker())

    def stop(self) -> None:
        if not self._loop:
            return
        self._stopping = True
        # Don't block the UI thread waiting for WinRT to unwind.
        self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._shutdown()))
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def submit(self, coro: Coroutine) -> "asyncio.Future":
        if not self._loop:
            raise RuntimeError("BLE loop not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def is_connected(self) -> bool:
        return bool(self._state.connected)

    def set_write_uuid(self, uuid: str) -> None:
        self._write_uuid = uuid

    def set_write_delay_ms(self, delay_ms: int) -> None:
        self._write_delay_s = max(0.0, int(delay_ms) / 1000.0)

    def set_last_device(self, *, address: str, name: str, write_uuid: str | None = None) -> None:
        self._last_device = {"address": address, "name": name, "write_uuid": write_uuid or self._write_uuid}

    async def scan(self, timeout: float = 5.0) -> list[DeviceInfo]:
        devices = await BleakScanner.discover(timeout=timeout)
        found: list[DeviceInfo] = []
        for d in devices:
            name = (d.name or "").strip()
            if NAME_SUBSTR.lower() in name.lower():
                found.append(DeviceInfo(address=d.address, name=name, rssi=getattr(d, "rssi", None), raw=d))
        found.sort(key=lambda x: (x.rssi is None, -(x.rssi or -999)))
        return found

    async def connect(
        self,
        address: str,
        name: str = "",
        write_uuid: Optional[str] = None,
        *,
        raw_device: Any | None = None,
    ) -> None:
        await self.disconnect()
        await self._ensure_worker()

        self._write_uuid = write_uuid or self._write_uuid
        self._state.last_error = None
        dev = DeviceInfo(address=address, name=name or address)
        self._emit_state(connected=False, device=dev)
        self._last_device = {"address": address, "name": dev.name, "write_uuid": self._write_uuid}

        last_exc: Exception | None = None
        for attempt in range(1, 4):
            client = self._make_client(raw_device or address)
            try:
                self._log(f"Connecting (attempt {attempt}/3) to {address}…")
                await client.connect(timeout=10.0)
                self._client = client
                await self._validate_write_characteristic()
                self._emit_state(connected=True, device=dev)
                self._log("Connected.")
                return
            except Exception as e:
                last_exc = e
                self._log(f"Connect failed: {e}")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                self._client = None
                await asyncio.sleep(0.25 * attempt)

        self._emit_state(connected=False, device=None, last_error=str(last_exc) if last_exc else "Connect failed")
        raise last_exc or RuntimeError("Connect failed")

    def _make_client(self, target: Any) -> BleakClient:
        # Bleak API differs across versions:
        # - some support BleakClient(..., disconnected_callback=...)
        # - others require client.set_disconnected_callback(...)
        try:
            client = BleakClient(target, disconnected_callback=self._on_disconnected)
        except TypeError:
            client = BleakClient(target)
            if hasattr(client, "set_disconnected_callback"):
                try:
                    client.set_disconnected_callback(self._on_disconnected)  # type: ignore[attr-defined]
                except Exception:
                    pass
        else:
            if hasattr(client, "set_disconnected_callback"):
                try:
                    client.set_disconnected_callback(self._on_disconnected)  # type: ignore[attr-defined]
                except Exception:
                    pass
        return client

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

    async def ensure_connection(self) -> None:
        if self._client and getattr(self._client, "is_connected", False):
            return
        if not self._last_device:
            raise RuntimeError("No last device configured")
        await self.connect(
            address=self._last_device["address"],
            name=self._last_device.get("name", ""),
            write_uuid=self._last_device.get("write_uuid", self._write_uuid),
        )

    async def safe_write(self, data: bytes, label: str = "") -> None:
        await self._ensure_worker()
        await self.ensure_connection()
        assert self._queue is not None
        await self._queue.put((data, label))

    async def write(self, data: bytes, label: str = "") -> None:
        # Back-compat: enqueue via worker.
        await self.safe_write(data, label=label)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._loop_ready.set()
        loop.run_forever()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

    async def _shutdown(self) -> None:
        if self._queue is not None:
            with contextlib.suppress(Exception):
                self._queue.put_nowait((b"", "__shutdown__"))
        try:
            await self.disconnect()
        except Exception:
            pass
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await self._worker_task

    def _on_disconnected(self, _client: BleakClient) -> None:
        self._emit_state(connected=False, last_error="Disconnected")
        self._log("Disconnected.")

    async def _ensure_worker(self) -> None:
        if self._queue is None:
            self._queue = asyncio.Queue()
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker(), name="ble-writer")

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            data, label = await self._queue.get()
            if self._stopping or label == "__shutdown__":
                return
            try:
                await self.ensure_connection()
                if not self._client:
                    raise RuntimeError("Not connected")
                await self._client.write_gatt_char(self._write_uuid, data, response=False)
                if self._on_last_command:
                    self._on_last_command(label or data.hex(" "))
                await asyncio.sleep(self._write_delay_s)
            except Exception as e:
                self._emit_state(connected=False, last_error=str(e))
                self._log(f"Write error: {e}")
                await asyncio.sleep(0.2)

    async def _validate_write_characteristic(self) -> None:
        if not self._client:
            return
        # Ensure the UUID exists on the device; fallback to finding a writable characteristic.
        services = await self._client.get_services()
        if self._write_uuid in services.characteristics:
            return
        for svc in services:
            for ch in svc.characteristics:
                props = {p.lower() for p in (ch.properties or [])}
                if "write-without-response" in props or "write" in props:
                    self._write_uuid = str(ch.uuid)
                    self._log(f"Write UUID not found; falling back to {self._write_uuid}")
                    return
        raise RuntimeError("Device has no writable characteristic")

    def _log(self, msg: str) -> None:
        if self._on_log:
            self._on_log(msg)

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
