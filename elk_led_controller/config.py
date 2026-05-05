from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "last_device": {
        "address": "",
        "name": "",
        "write_uuid": "0000fff3-0000-1000-8000-00805f9b34fb",
    },
    "last_color": [255, 100, 0],
    "last_brightness": 80,
    "recent_colors": [],
    "scenes": [],
}


@dataclass
class AppConfig:
    path: Path
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        path = Path(path)
        if not path.exists():
            cfg = cls(path=path, data=json.loads(json.dumps(DEFAULT_CONFIG)))
            cfg.save()
            return cfg
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        _deep_update(merged, data if isinstance(data, dict) else {})
        return cls(path=path, data=merged)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, sort_keys=False)


def _deep_update(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)  # type: ignore[index]
        else:
            dst[k] = v

