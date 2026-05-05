from __future__ import annotations

import asyncio
import threading
from typing import Coroutine


class AsyncRunner:
    def __init__(self, name: str = "async-runner") -> None:
        self._name = name
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        if not self._loop:
            raise RuntimeError("Async loop failed to start")

    def stop(self) -> None:
        if not self._loop:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)

    def submit(self, coro: Coroutine):
        if not self._loop:
            raise RuntimeError("Runner not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

