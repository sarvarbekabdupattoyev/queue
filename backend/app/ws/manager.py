import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    """Room-based WebSocket fanout.

    Rooms: ``display:{event_id}`` (public payloads) and ``staff:{event_id}``
    (payloads with names/phones for authenticated staff).
    """

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, room: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms[room].add(websocket)

    async def disconnect(self, room: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._rooms[room].discard(websocket)
            if not self._rooms[room]:
                self._rooms.pop(room, None)

    async def broadcast(self, room: str, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, ensure_ascii=False, default=str)
        async with self._lock:
            sockets = list(self._rooms.get(room, ()))
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(message)
            except Exception:  # client vanished mid-send
                dead.append(ws)
        for ws in dead:
            await self.disconnect(room, ws)


ws_manager = ConnectionManager()
