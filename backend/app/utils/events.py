"""Hub WebSocket: siaran event real-time dari thread mana pun (endpoint sync, worker)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("asf.events")


class EventHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        text = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(text)
            except Exception:  # noqa: BLE001 - klien terputus
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    def publish(self, type_: str, data: dict[str, Any] | None = None) -> None:
        """Thread-safe. Tidak melakukan apa pun bila belum ada loop / klien."""
        loop = self._loop
        if loop is None or loop.is_closed() or not self._clients:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast({"type": type_, "data": data or {}}), loop)


hub = EventHub()
