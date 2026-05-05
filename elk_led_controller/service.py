from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .ble_controller import BleController
from .protocol import cmd_brightness, cmd_effect, cmd_power, cmd_rgb


@dataclass
class LedState:
    power_on: bool = True
    r: int = 255
    g: int = 100
    b: int = 0
    brightness_pct: int = 80
    effect_mode: int = 0
    effect_speed: int = 120


class LedService:
    def __init__(self, ble: BleController, state: LedState | None = None) -> None:
        self._ble = ble
        self.state = state or LedState()

    def set_power(self, on: bool) -> None:
        self.state.power_on = bool(on)
        self._ble.submit(self._ble.safe_write(cmd_power(self.state.power_on), label="Power"))

    def set_color(self, r: int, g: int, b: int) -> None:
        self.state.r = int(max(0, min(255, r)))
        self.state.g = int(max(0, min(255, g)))
        self.state.b = int(max(0, min(255, b)))
        self._ble.submit(self._ble.safe_write(cmd_rgb(self.state.r, self.state.g, self.state.b), label="RGB"))

    def set_brightness_pct(self, pct: int) -> None:
        self.state.brightness_pct = int(max(0, min(100, pct)))
        val = int(round(self.state.brightness_pct * 255 / 100))
        self._ble.submit(self._ble.safe_write(cmd_brightness(val), label="Brightness"))

    def set_effect(self, mode: int, speed: int) -> None:
        self.state.effect_mode = int(max(0, min(0x17, mode)))
        self.state.effect_speed = int(max(0, min(255, speed)))
        self._ble.submit(self._ble.safe_write(cmd_effect(self.state.effect_mode, self.state.effect_speed), label="Effect"))

    async def ping(self) -> None:
        # lightweight: just ensure connection
        await self._ble.ensure_connection()

