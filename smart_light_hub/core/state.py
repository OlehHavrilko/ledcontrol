from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StateEntry:
    entity_id: str
    value: dict[str, Any]
    updated_at: float
    version: int


class StateStore:
    def __init__(self) -> None:
        self._data: dict[str, StateEntry] = {}
        self._version = 0

    def get(self, entity_id: str) -> dict[str, Any] | None:
        entry = self._data.get(entity_id)
        return None if entry is None else dict(entry.value)

    def entry(self, entity_id: str) -> StateEntry | None:
        return self._data.get(entity_id)

    def set(self, entity_id: str, value: dict[str, Any]) -> StateEntry:
        self._version += 1
        entry = StateEntry(
            entity_id=entity_id,
            value=dict(value),
            updated_at=time.time(),
            version=self._version,
        )
        self._data[entity_id] = entry
        return entry

    def all(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v.value) for k, v in self._data.items()}

