from __future__ import annotations

from dataclasses import dataclass

from elk_led_controller.ble_controller import BleController, WRITE_UUID_DEFAULT


@dataclass(frozen=True)
class DiscoveredBleDevice:
    address: str
    name: str
    rssi: int | None = None
    kind: str = "elk_bledom"
    write_uuid: str = WRITE_UUID_DEFAULT


async def discover_elk_bledom(ble: BleController, timeout: float = 5.0) -> list[DiscoveredBleDevice]:
    found = await ble.scan(timeout=timeout)
    return [DiscoveredBleDevice(address=d.address, name=d.name, rssi=d.rssi) for d in found]

