from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ..core.engine import CoreEngine


async def state_websocket(engine: CoreEngine, ws: WebSocket) -> None:
    await ws.accept()

    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def on_state(evt) -> None:
        await q.put({"type": "event", "name": evt.name, "data": evt.data})

    unsub_state = engine.events.subscribe("state_changed", on_state)
    unsub_applied = engine.events.subscribe("device_applied", on_state)
    unsub_missing = engine.events.subscribe("device_missing", on_state)

    try:
        await ws.send_text(json.dumps({"type": "snapshot", "state": engine.state.all()}))
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=20)
                await ws.send_text(json.dumps(msg))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        return
    finally:
        unsub_state()
        unsub_applied()
        unsub_missing()

