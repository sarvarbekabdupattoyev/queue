"""WebSocket fan-out.

Rooms: ``display:{event_id}`` (public payloads) and ``staff:{event_id}``
(payloads with names/phones for authenticated staff).

Single-process mode (no Redis): ``publish`` delivers straight to local
sockets. Multi-process mode: ``publish`` goes through Redis pub/sub and every
API worker runs :meth:`run_subscriber`, so each worker delivers to the
sockets *it* holds — this is what makes ``uvicorn --workers N`` safe.
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.core.redis import CH_WS, get_redis

log = logging.getLogger(__name__)


class ConnectionManager:
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

    async def deliver_local(self, room: str, message: str) -> None:
        """Send a serialized payload to sockets held by this process."""
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

    async def publish(self, room: str, payload: dict[str, Any]) -> None:
        """Broadcast to every connected client in the room, across workers."""
        message = json.dumps(payload, ensure_ascii=False, default=str)
        redis = get_redis()
        if redis is None:
            await self.deliver_local(room, message)
            return
        try:
            await redis.publish(CH_WS, json.dumps({"room": room, "message": message}))
        except Exception as exc:
            log.warning("Redis publish failed (%s); delivering locally only", exc)
            await self.deliver_local(room, message)

    async def run_subscriber(self) -> None:
        """Background task per process: relay Redis pub/sub into local rooms.
        Reconnects forever with backoff."""
        delay = 1.0
        while True:
            redis = get_redis()
            if redis is None:
                return
            try:
                pubsub = redis.pubsub()
                await pubsub.subscribe(CH_WS)
                delay = 1.0
                async for item in pubsub.listen():
                    if item.get("type") != "message":
                        continue
                    try:
                        envelope = json.loads(item["data"])
                        await self.deliver_local(envelope["room"], envelope["message"])
                    except Exception:
                        log.exception("Malformed WS pub/sub envelope")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("WS subscriber lost Redis (%s); retrying in %.0fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 15.0)


ws_manager = ConnectionManager()
