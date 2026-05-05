from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elk_led_controller.ble_controller import BleController, WRITE_UUID_DEFAULT
from elk_led_controller.protocol import cmd_brightness, cmd_effect, cmd_power, cmd_rgb

from .base import BaseDevice, DeviceCapabilities


@dataclass(frozen=True)
class ElkConfig:
    address: str
    name: str = "ELK-BLEDOM"
    write_uuid: str = WRITE_UUID_DEFAULT


class ElkBledomDevice(BaseDevice):
    kind = "elk_bledom"

    def __init__(self, *, entity_id: str, cfg: ElkConfig, ble: BleController) -> None:
        super().__init__(
            entity_id=entity_id,
            name=cfg.name,
            capabilities=DeviceCapabilities(power=True, rgb=True, brightness=True, effects=True),
        )
        self._cfg = cfg
        self._ble = ble

    async def connect(self) -> None:
        self._ble.set_last_device(address=self._cfg.address, name=self._cfg.name, write_uuid=self._cfg.write_uuid)
        await self._ble.connect(address=self._cfg.address, name=self._cfg.name, write_uuid=self._cfg.write_uuid)

    async def disconnect(self) -> None:
        await self._ble.disconnect()

    async def apply_state(self, state: dict[str, Any]) -> None:
        # Apply minimal required writes; order matters for some strips.
        on = bool(state.get("on", True))
        await self._ble.safe_write(cmd_power(on), label=f"{self.entity_id}:power")

        if "color" in state:
            r, g, b = state.get("color") or [255, 255, 255]
            await self._ble.safe_write(cmd_rgb(int(r), int(g), int(b)), label=f"{self.entity_id}:rgb")

        if "brightness" in state:
            pct = int(state.get("brightness") or 100)
            pct = max(0, min(100, pct))
            val = int(round(pct * 255 / 100))
            await self._ble.safe_write(cmd_brightness(val), label=f"{self.entity_id}:brightness")

        if "effect" in state:
            eff = state.get("effect") or {}
            mode = int(eff.get("mode") or 0)
            speed = int(eff.get("speed") or 120)
            await self._ble.safe_write(cmd_effect(mode, speed), label=f"{self.entity_id}:effect")

