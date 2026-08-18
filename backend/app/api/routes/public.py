from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import SaleEvent, Ticket
from app.services import queue_service
from app.services.qr_service import qr_data_url

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/display/{display_code}")
async def display_state(display_code: str, db: DbSession) -> dict:
    """State for the office TV board — numbers only, no personal data."""
    event = await db.scalar(select(SaleEvent).where(SaleEvent.display_code == display_code))
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ekran topilmadi")
    return await queue_service.build_public_state(db, event)


@router.get("/tickets/{code}")
async def ticket_state(code: str, db: DbSession) -> dict:
    """A client's own ticket page (linked from the bot). Looked up by the
    unguessable QR code, so it may include the client's first name."""
    ticket = await db.scalar(select(Ticket).where(Ticket.code == code))
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Navbat topilmadi")
    event = await db.get(SaleEvent, ticket.event_id)
    position = await queue_service.position_of(db, ticket)
    desk_numbers = await queue_service.desk_numbers_for(db, [ticket])
    waiting = await queue_service.waiting_tickets(db, event.id)
    return {
        "number": ticket.number,
        "first_name": ticket.first_name,
        "status": ticket.status.value,
        "late": ticket.late,
        "position": position,
        "waiting_count": len(waiting),
        "desk_number": desk_numbers.get(ticket.desk_id),
        "qr": qr_data_url(ticket.code),
        "event": {
            "name": event.name,
            "phase": event.phase().value,
            "starts_at": event.starts_at.isoformat(),
            "checkin_until": event.checkin_until.isoformat(),
        },
    }
