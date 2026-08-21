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
from contextlib import suppress
from typing import Any

from fastapi import WebSocket

from app.core.redis import CH_WS, get_redis

log = logging.getLogger(__name__)

# A screen that cannot accept a payload within this window is dropped and left
# to reconnect (the client already reconnects and re-snapshots). Without a cap
# one stalled socket holds up every other screen in the room.
SEND_TIMEOUT_S = 5.0


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
        """Send a serialized payload to sockets held by this process.

        Sends run concurrently and each is capped by ``SEND_TIMEOUT_S``:
        awaiting them one after another lets a single stalled client (a TV on a
        saturated uplink) delay every other screen in the room — and, in
        multi-process mode, block the Redis subscriber loop that feeds them.
        """
        async with self._lock:
            sockets = list(self._rooms.get(room, ()))
        if not sockets:
            return
        delivered = await asyncio.gather(
            *(self._send(ws, message) for ws in sockets), return_exceptions=True
        )
        for ws, ok in zip(sockets, delivered):
            if ok is not True:  # vanished, stalled, or already closed
                await self.disconnect(room, ws)

    async def _send(self, websocket: WebSocket, message: str) -> bool:
        try:
            await asyncio.wait_for(websocket.send_text(message), SEND_TIMEOUT_S)
            return True
        except Exception:
            return False

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
            pubsub = redis.pubsub()
            try:
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
            finally:
                # every reconnect otherwise strands the previous subscription's
                # connection — a flapping Redis leaks one per attempt
                with suppress(Exception):
                    await pubsub.aclose()


ws_manager = ConnectionManager()
