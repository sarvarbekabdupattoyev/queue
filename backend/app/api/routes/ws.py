import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.session import SessionFactory
from app.models import SaleEvent, User, UserRole
from app.services import queue_service
from app.ws.manager import ws_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["ws"])

STAFF_ROLES = (UserRole.OWNER, UserRole.MANAGER, UserRole.SCANNER)


async def _hold(websocket: WebSocket, room: str) -> None:
    """Keep the socket registered until the client disconnects.

    Clients may send anything (e.g. "ping"); it is ignored — state flows
    one way, server → client.
    """
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(room, websocket)


async def _open(websocket: WebSocket, room: str, state: dict) -> bool:
    """Register the socket and hand it the current state.

    A failed first send (screen already gone, uplink stalled) must not leave
    the socket sitting in the room: nothing would ever remove it, and the room
    would keep growing across a day of flaky reconnects.
    """
    await ws_manager.connect(room, websocket)
    try:
        await websocket.send_json(state)
    except Exception:
        await ws_manager.disconnect(room, websocket)
        return False
    return True


@router.websocket("/display/{display_code}")
async def display_ws(websocket: WebSocket, display_code: str) -> None:
    # The state is built and the pooled database connection handed back BEFORE
    # the socket work — a screen on a slow uplink must never pin a connection
    # for the length of a multi-megabyte send.
    async with SessionFactory() as db:
        event = await db.scalar(
            select(SaleEvent).where(SaleEvent.display_code == display_code)
        )
        if event is None:
            await websocket.close(code=4404)
            return
        room = f"display:{event.id}"
        state = await queue_service.build_public_state(db, event)
    if not await _open(websocket, room, state):
        return
    await _hold(websocket, room)


@router.websocket("/staff/{event_id}")
async def staff_ws(websocket: WebSocket, event_id: int, token: str = "") -> None:
    user_id = decode_access_token(token)
    if user_id is None:
        await websocket.close(code=4401)
        return
    async with SessionFactory() as db:
        user = await db.get(User, user_id)
        event = await db.get(SaleEvent, event_id)
        if (
            user is None
            or not user.is_active
            or user.role not in STAFF_ROLES
            or event is None
            or event.company_id != user.company_id
        ):
            await websocket.close(code=4403)
            return
        room = f"staff:{event.id}"
        state = await queue_service.build_staff_state(db, event)
    if not await _open(websocket, room, state):
        return
    await _hold(websocket, room)
