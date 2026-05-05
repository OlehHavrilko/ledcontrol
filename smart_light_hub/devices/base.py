from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeviceCapabilities:
    power: bool = True
    rgb: bool = True
    brightness: bool = True
    effects: bool = True


class BaseDevice:
    def __init__(self, *, entity_id: str, name: str, capabilities: DeviceCapabilities | None = None) -> None:
        self.entity_id = entity_id
        self.name = name
        self.capabilities = capabilities or DeviceCapabilities()

    async def connect(self) -> None:
        return

    async def disconnect(self) -> None:
        return

    async def apply_state(self, state: dict[str, Any]) -> None:
        raise NotImplementedError

