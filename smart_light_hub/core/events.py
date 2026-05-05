from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    name: str
    data: dict[str, Any]


Listener = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = {}

    def subscribe(self, event_name: str, callback: Listener) -> None:
        self._listeners.setdefault(event_name, []).append(callback)

    async def emit(self, event_name: str, data: dict[str, Any]) -> None:
        event = Event(name=event_name, data=dict(data))
        listeners = list(self._listeners.get(event_name, []))
        if not listeners:
            return
        await asyncio.gather(*(cb(event) for cb in listeners), return_exceptions=True)

