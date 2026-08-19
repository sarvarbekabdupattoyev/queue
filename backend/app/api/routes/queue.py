from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CompanyEvent, DbSession, ManagerUser, StaffUser, require_roles
from app.models import Branch, Desk, Ticket, User, UserRole
from app.schemas.event import CallNextRequest, CheckinRequest, TicketActionRequest, TicketOut
from app.services import queue_service
from app.services.errors import DomainError

router = APIRouter(prefix="/queue", tags=["queue"])

AnyStaff = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.SCANNER))
ManagerOnly = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER))


def _out(ticket: Ticket, desk_number: int | None = None, position: int | None = None) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    out.desk_number = desk_number
    out.position = position
    return out


def _raise(exc: DomainError) -> None:
    raise HTTPException(exc.status_code, exc.message) from None


def _assert_same_branch(ticket: Ticket, user: User) -> None:
    """Branch staff only ever act on their own branch's clients."""
    if (
        ticket.branch_id is not None
        and user.branch_id is not None
        and ticket.branch_id != user.branch_id
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Bu navbat boshqa filialga tegishli"
        )


@router.post("/{event_id}/checkin")
async def check_in(
    payload: CheckinRequest, db: DbSession, event: CompanyEvent, user: StaffUser
) -> dict:
    """QR scanned (code) or 4-letter code entered manually at the reception."""
    ticket = None
    if payload.code:
        code = payload.code.strip()
        ticket = await db.scalar(
            select(Ticket).where(Ticket.code == code, Ticket.event_id == event.id)
        )
    elif payload.number is not None:
        ticket = await db.scalar(
            select(Ticket).where(Ticket.event_id == event.id, Ticket.number == payload.number)
        )
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bunday navbat topilmadi")
    # branch staff must not check in a client who queued at another branch —
    # their spot in the queue lives at that branch
    if (
        ticket.branch_id is not None
        and user.branch_id is not None
        and ticket.branch_id != user.branch_id
    ):
        branch = await db.get(Branch, ticket.branch_id)
        branch_name = branch.name if branch else "boshqa"
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Bu navbat «{branch_name}» filialiga tegishli — mijoz o'sha filialga borishi kerak",
        )
    try:
        result = await queue_service.check_in(db, event, ticket)
    except DomainError as exc:
        _raise(exc)
    position = await queue_service.position_of(db, ticket)
    return {
        "ok": result["ok"],
        "kind": result["kind"],
        "message": result["message"],
        "ticket": _out(ticket, position=position),
    }


@router.post("/{event_id}/call")
async def call_next(
    payload: CallNextRequest, db: DbSession, event: CompanyEvent, user: ManagerUser
) -> dict:
    desk = await db.get(Desk, payload.desk_id)
    if desk is None or desk.company_id != event.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stol topilmadi")
    # a branch manager calls only at desks of their own branch
    if (
        user.role == UserRole.MANAGER
        and user.branch_id is not None
        and desk.branch_id != user.branch_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu stol boshqa filialga tegishli")
    try:
        ticket = await queue_service.call_next(db, event, desk)
    except DomainError as exc:
        _raise(exc)
    if ticket is None:
        return {"ok": False, "message": "Navbatda hech kim yo'q (kelganlar orasida)", "ticket": None}
    return {
        "ok": True,
        "message": f"№{ticket.number} chaqirildi",
        "ticket": _out(ticket, desk_number=desk.number),
    }


async def _load_ticket(db: DbSession, event, number: str, user: User) -> Ticket:
    """Resolve a ticket by its code inside the event, refusing tickets that
    belong to another branch than the acting staff member."""
    try:
        ticket = await queue_service.get_ticket_by_number(db, event.id, number)
    except DomainError as exc:
        _raise(exc)
    _assert_same_branch(ticket, user)
    return ticket


@router.post("/{event_id}/recall")
async def recall(
    payload: TicketActionRequest, db: DbSession, event: CompanyEvent, user: ManagerUser
) -> dict:
    ticket = await _load_ticket(db, event, payload.number, user)
    try:
        await queue_service.recall(db, event, ticket)
    except DomainError as exc:
        _raise(exc)
    return {"ok": True, "message": "Takroriy chaqiruv yuborildi", "ticket": _out(ticket)}


@router.post("/{event_id}/serving")
async def serving(
    payload: TicketActionRequest, db: DbSession, event: CompanyEvent, user: ManagerUser
) -> dict:
    ticket = await _load_ticket(db, event, payload.number, user)
    try:
        await queue_service.start_serving(db, event, ticket)
    except DomainError as exc:
        _raise(exc)
    return {"ok": True, "message": f"№{ticket.number} — xizmat boshlandi", "ticket": _out(ticket)}


@router.post("/{event_id}/skip")
async def skip(
    payload: TicketActionRequest, db: DbSession, event: CompanyEvent, user: ManagerUser
) -> dict:
    ticket = await _load_ticket(db, event, payload.number, user)
    try:
        await queue_service.skip(db, event, ticket)
    except DomainError as exc:
        _raise(exc)
    return {"ok": True, "message": f"№{ticket.number} o'tkazib yuborildi", "ticket": _out(ticket)}


@router.post("/{event_id}/done")
async def done(
    payload: TicketActionRequest, db: DbSession, event: CompanyEvent, user: ManagerUser
) -> dict:
    ticket = await _load_ticket(db, event, payload.number, user)
    try:
        await queue_service.finish(db, event, ticket)
    except DomainError as exc:
        _raise(exc)
    return {"ok": True, "message": f"№{ticket.number} yakunlandi", "ticket": _out(ticket)}


@router.post("/{event_id}/cancel")
async def cancel(
    payload: TicketActionRequest,
    db: DbSession,
    event: CompanyEvent,
    user: Annotated[User, Depends(require_roles(UserRole.OWNER))],
) -> dict:
    ticket = await _load_ticket(db, event, payload.number, user)
    try:
        await queue_service.cancel(db, event, ticket)
    except DomainError as exc:
        _raise(exc)
    return {"ok": True, "message": f"№{ticket.number} bekor qilindi", "ticket": _out(ticket)}
