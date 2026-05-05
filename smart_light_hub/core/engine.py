from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..utils.async_tools import AsyncRunner
from .events import EventBus
from .registry import DeviceRegistry
from .state import StateStore


@dataclass
class EngineConfig:
    pass


class CoreEngine:
    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self.state = StateStore()
        self.events = EventBus()
        self.registry = DeviceRegistry()
        self.runner = AsyncRunner(name="hub-loop")

    def start(self) -> None:
        self.runner.start()

    def stop(self) -> None:
        self.runner.stop()

    def submit(self, coro):
        return self.runner.submit(coro)

