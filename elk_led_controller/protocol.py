from __future__ import annotations

from dataclasses import dataclass


START = 0x7E
END = 0xEF


def _frame(payload: list[int]) -> bytes:
    return bytes([START, 0x00, *payload, 0x00, END])


def cmd_power(on: bool) -> bytes:
    # Common ELK-BLEDOM 9-byte variant.
    return _frame([0x04, 0xF0 if on else 0x00, 0x00, 0x01 if on else 0x00, 0xFF])


def cmd_rgb(r: int, g: int, b: int) -> bytes:
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return _frame([0x05, 0x03, r, g, b])


def cmd_brightness(brightness_0_255: int) -> bytes:
    val = max(0, min(255, int(brightness_0_255)))
    return _frame([0x01, val, 0x00, 0x00, 0x00])


def cmd_effect(mode: int, speed: int) -> bytes:
    mode = max(0, min(0x17, int(mode)))
    speed = max(0, min(255, int(speed)))
    return _frame([0x03, mode, speed, 0x00, 0x00])


@dataclass(frozen=True)
class DeviceInfo:
    address: str
    name: str
    rssi: int | None = None

