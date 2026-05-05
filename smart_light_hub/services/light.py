from __future__ import annotations

from typing import Any

from ..core.engine import CoreEngine


class LightService:
    def __init__(self, engine: CoreEngine) -> None:
        self.engine = engine

    async def set_state(self, entity_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.engine.state.get(entity_id) or {}
        new_state = dict(current)
        new_state.update(patch)
        entry = self.engine.state.set(entity_id, new_state)
        await self.engine.events.emit("state_changed", {"entity_id": entity_id, "state": entry.value, "version": entry.version})

        device = self.engine.registry.get(entity_id)
        if not device:
            await self.engine.events.emit("device_missing", {"entity_id": entity_id})
            return entry.value
        await device.apply_state(entry.value)
        await self.engine.events.emit("device_applied", {"entity_id": entity_id})
        return entry.value

    async def turn_on(self, entity_id: str) -> dict[str, Any]:
        return await self.set_state(entity_id, {"on": True})

    async def turn_off(self, entity_id: str) -> dict[str, Any]:
        return await self.set_state(entity_id, {"on": False})

    async def set_color(self, entity_id: str, r: int, g: int, b: int) -> dict[str, Any]:
        rgb = [int(max(0, min(255, r))), int(max(0, min(255, g))), int(max(0, min(255, b)))]
        return await self.set_state(entity_id, {"color": rgb})

    async def set_brightness(self, entity_id: str, pct: int) -> dict[str, Any]:
        return await self.set_state(entity_id, {"brightness": int(max(0, min(100, pct)))})

    async def set_effect(self, entity_id: str, mode: int, speed: int) -> dict[str, Any]:
        return await self.set_state(entity_id, {"effect": {"mode": int(mode), "speed": int(speed)}})

