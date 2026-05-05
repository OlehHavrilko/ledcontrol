from __future__ import annotations

import json
from pathlib import Path

import uvicorn

from elk_led_controller.ble_controller import BleController

from .api.http import create_app
from .core.engine import CoreEngine
from .core.registry import DeviceDescriptor
from .devices.elk_bledom import ElkBledomDevice, ElkConfig
from .ui.app import HubApp


def _load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing config: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    cfg_path = Path("smart_light_hub/storage/config.json")
    cfg = _load_config(cfg_path)

    engine = CoreEngine()
    engine.start()

    # Transport(s)
    ble = BleController()
    ble.start()

    # Devices from config
    for d in cfg.get("devices", []) or []:
        kind = d.get("kind")
        if kind != "elk_bledom":
            continue
        entity_id = str(d.get("entity_id") or "light.elk")
        elk_cfg = ElkConfig(
            address=str(d.get("address")),
            name=str(d.get("name") or "ELK-BLEDOM"),
            write_uuid=str(d.get("write_uuid") or ""),
        )
        if d.get("write_delay_ms") is not None:
            ble.set_write_delay_ms(int(d["write_delay_ms"]))
        dev = ElkBledomDevice(entity_id=entity_id, cfg=elk_cfg, ble=ble)
        engine.registry.register(
            entity_id,
            dev,
            DeviceDescriptor(entity_id=entity_id, name=elk_cfg.name, kind=ElkBledomDevice.kind, meta={"address": elk_cfg.address}),
        )
        # Seed state
        engine.state.set(entity_id, {"on": True, "brightness": 80, "color": [255, 100, 0]})

    # Optional HTTP API (runs in separate thread via uvicorn internal loop)
    http = cfg.get("http_api", {}) or {}
    if bool(http.get("enabled", False)):
        app = create_app(engine)
        uvicorn.run(app, host=str(http.get("host") or "127.0.0.1"), port=int(http.get("port") or 8787), log_level="warning")
        return

    # Desktop UI
    app = HubApp(engine)
    app.mainloop()


if __name__ == "__main__":
    main()

