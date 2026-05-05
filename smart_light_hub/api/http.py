from __future__ import annotations

from fastapi import FastAPI
from fastapi import WebSocket

from ..core.engine import CoreEngine
from ..services.light import LightService
from .websocket import state_websocket


def create_app(engine: CoreEngine) -> FastAPI:
    app = FastAPI(title="Smart Light Hub")
    light = LightService(engine)

    @app.get("/state")
    def state_all():
        return engine.state.all()

    @app.get("/devices")
    def devices():
        return [d.__dict__ for d in engine.registry.list()]

    @app.post("/light/{entity_id}/on")
    async def light_on(entity_id: str):
        return await light.turn_on(entity_id)

    @app.post("/light/{entity_id}/off")
    async def light_off(entity_id: str):
        return await light.turn_off(entity_id)

    @app.post("/light/{entity_id}/color")
    async def light_color(entity_id: str, r: int, g: int, b: int):
        return await light.set_color(entity_id, r, g, b)

    @app.post("/light/{entity_id}/brightness")
    async def light_brightness(entity_id: str, pct: int):
        return await light.set_brightness(entity_id, pct)

    @app.post("/light/{entity_id}/effect")
    async def light_effect(entity_id: str, mode: int, speed: int):
        return await light.set_effect(entity_id, mode, speed)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await state_websocket(engine, ws)

    return app
