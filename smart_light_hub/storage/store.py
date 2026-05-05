from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_HUB_CONFIG: dict[str, Any] = {
    "http_api": {"enabled": False, "host": "127.0.0.1", "port": 8787},
    "devices": [],
}


def _deep_update(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)  # type: ignore[index]
        else:
            dst[k] = v


@dataclass
class HubConfigStore:
    path: Path
    data: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> "HubConfigStore":
        path = Path(path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(DEFAULT_HUB_CONFIG, indent=2), encoding="utf-8")
        raw = json.loads(path.read_text(encoding="utf-8"))
        merged = json.loads(json.dumps(DEFAULT_HUB_CONFIG))
        if isinstance(raw, dict):
            _deep_update(merged, raw)
        return cls(path=path, data=merged)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def upsert_device(self, device: dict[str, Any]) -> None:
        devices: list[dict[str, Any]] = list(self.data.get("devices", []) or [])
        entity_id = str(device.get("entity_id") or "")
        devices = [d for d in devices if str(d.get("entity_id") or "") != entity_id]
        devices.insert(0, device)
        self.data["devices"] = devices
        self.save()

