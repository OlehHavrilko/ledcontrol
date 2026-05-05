from __future__ import annotations

import threading
from dataclasses import dataclass

from fastapi import FastAPI
import uvicorn

from .service import LedService


@dataclass(frozen=True)
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8787


def create_app(service: LedService) -> FastAPI:
    app = FastAPI(title="ELK-BLEDOM LED Controller API")

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        await service.ping()
        return {"status": "ok"}

    @app.post("/power")
    def power(on: bool) -> dict[str, bool]:
        service.set_power(on)
        return {"on": on}

    @app.post("/color")
    def color(r: int, g: int, b: int) -> dict[str, int]:
        service.set_color(r, g, b)
        return {"r": r, "g": g, "b": b}

    @app.post("/brightness")
    def brightness(pct: int) -> dict[str, int]:
        service.set_brightness_pct(pct)
        return {"pct": pct}

    @app.post("/effect")
    def effect(mode: int, speed: int) -> dict[str, int]:
        service.set_effect(mode, speed)
        return {"mode": mode, "speed": speed}

    return app


def start_api_in_thread(service: LedService, cfg: ApiConfig) -> threading.Thread:
    app = create_app(service)

    def run() -> None:
        uvicorn.run(app, host=cfg.host, port=int(cfg.port), log_level="warning")

    t = threading.Thread(target=run, name="http-api", daemon=True)
    t.start()
    return t

