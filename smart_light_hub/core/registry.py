from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeviceDescriptor:
    entity_id: str
    name: str
    kind: str
    meta: dict[str, Any]


class DeviceRegistry:
    def __init__(self) -> None:
        self._devices: dict[str, Any] = {}
        self._descriptors: dict[str, DeviceDescriptor] = {}

    def register(self, entity_id: str, device: Any, desc: DeviceDescriptor) -> None:
        self._devices[entity_id] = device
        self._descriptors[entity_id] = desc

    def get(self, entity_id: str):
        return self._devices.get(entity_id)

    def list(self) -> list[DeviceDescriptor]:
        return list(self._descriptors.values())

