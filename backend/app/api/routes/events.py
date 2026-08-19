from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select

from app.api.deps import CompanyEvent, DbSession, OwnCompany, require_roles
from app.models import (
    Branch,
    Desk,
    SaleEvent,
    Ticket,
    TicketSource,
    TicketStatus,
    UserRole,
)
from app.schemas.event import (
    EventBranchOut,
    EventCreate,
    EventOut,
    EventUpdate,
    SeedRequest,
    TicketOut,
)
from app.services import queue_service, ticket_service

router = APIRouter(prefix="/events", tags=["events"])

OwnerOnly = Depends(require_roles(UserRole.OWNER))
AnyStaff = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.SCANNER))

SEED_NAMES = [
    ("Dilnoza", "Xolmatova"), ("Sardor", "Rahimov"), ("Malika", "Yusupova"),
    ("Bobur", "Karimov"), ("Nilufar", "Tosheva"), ("Jasur", "Aliyev"),
    ("Gulnora", "Saidova"), ("Otabek", "Ergashev"), ("Zilola", "Qodirova"),
    ("Sherzod", "Mirzayev"),
]


async def _event_out(db: DbSession, event: SaleEvent) -> EventOut:
    counts = (
        await db.execute(
            select(Ticket.status, func.count())
            .where(Ticket.event_id == event.id)
            .group_by(Ticket.status)
        )
    ).all()
    by_status = dict(counts)
    total = sum(c for s, c in by_status.items() if s != TicketStatus.CANCELLED)
    checked_in = sum(
        c for s, c in by_status.items()
        if s not in (TicketStatus.REGISTERED, TicketStatus.CANCELLED)
    )
    return EventOut(
        id=event.id,
        name=event.name,
        starts_at=event.starts_at,
        checkin_until=event.checkin_until,
        is_active=event.is_active,
        display_code=event.display_code,
        phase=event.phase(),
        branches=[EventBranchOut.model_validate(b) for b in event.branches],
        ticket_count=total,
        checked_in_count=checked_in,
    )


async def _load_branches(db: DbSession, company_id: int, branch_ids: list[int]) -> list[Branch]:
    """Resolve requested branch ids to this company's branches (order kept)."""
    unique_ids = list(dict.fromkeys(branch_ids))
    if not unique_ids:
        return []
    branches = (
        await db.scalars(
            select(Branch).where(Branch.company_id == company_id, Branch.id.in_(unique_ids))
        )
    ).all()
    if len(branches) != len(unique_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Filial topilmadi")
    by_id = {b.id: b for b in branches}
    return [by_id[i] for i in unique_ids]


def _ticket_out(ticket: Ticket, desk_numbers: dict[int, int], position: int | None = None) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    out.desk_number = desk_numbers.get(ticket.desk_id) if ticket.desk_id else None
    out.position = position
    return out


@router.get("", response_model=list[EventOut], dependencies=[AnyStaff])
async def list_events(db: DbSession, company: OwnCompany) -> list[EventOut]:
    events = (
        await db.scalars(
            select(SaleEvent)
            .where(SaleEvent.company_id == company.id)
            .order_by(SaleEvent.starts_at.desc())
        )
    ).all()
    return [await _event_out(db, e) for e in events]


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def create_event(payload: EventCreate, db: DbSession, company: OwnCompany) -> EventOut:
    branches = await _load_branches(db, company.id, payload.branch_ids)
    event = SaleEvent(
        company_id=company.id,
        name=payload.name.strip(),
        starts_at=payload.starts_at,
        checkin_until=payload.checkin_until,
        branches=branches,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return await _event_out(db, event)


@router.get("/{event_id}", response_model=EventOut, dependencies=[AnyStaff])
async def get_event(db: DbSession, event: CompanyEvent) -> EventOut:
    return await _event_out(db, event)


@router.patch("/{event_id}", response_model=EventOut, dependencies=[OwnerOnly])
async def update_event(payload: EventUpdate, db: DbSession, event: CompanyEvent) -> EventOut:
    if payload.name is not None:
        event.name = payload.name.strip()
    if payload.starts_at is not None:
        if payload.starts_at.tzinfo is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vaqt mintaqasi ko'rsatilmagan")
        event.starts_at = payload.starts_at
    if payload.checkin_until is not None:
        if payload.checkin_until.tzinfo is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vaqt mintaqasi ko'rsatilmagan")
        event.checkin_until = payload.checkin_until
    if event.checkin_until <= event.starts_at:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Skanerlash tugash vaqti boshlanish vaqtidan keyin bo'lishi kerak",
        )
    if payload.is_active is not None:
        event.is_active = payload.is_active
    if payload.branch_ids is not None:
        branches = await _load_branches(db, event.company_id, payload.branch_ids)
        # a branch that already holds tickets owns a slice of the queue —
        # removing it would strand those clients
        kept = {b.id for b in branches}
        removed = [b.id for b in event.branches if b.id not in kept]
        if removed:
            has_tickets = await db.scalar(
                select(Ticket.id)
                .where(
                    Ticket.event_id == event.id,
                    Ticket.branch_id.in_(removed),
                    Ticket.status != TicketStatus.CANCELLED,
                )
                .limit(1)
            )
            if has_tickets is not None:
                await db.rollback()
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Navbatlari bor filialni tadbirdan chiqarib bo'lmaydi",
                )
        # Turning an unscoped event into a branch event would strand the
        # tickets registered before it: they carry no branch, so no desk —
        # which always serves one branch — could ever call them.
        if branches and not event.branches:
            unscoped = await db.scalar(
                select(Ticket.id)
                .where(
                    Ticket.event_id == event.id,
                    Ticket.branch_id.is_(None),
                    Ticket.status != TicketStatus.CANCELLED,
                )
                .limit(1)
            )
            if unscoped is not None:
                await db.rollback()
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Bu tadbirda filialsiz navbatlar bor — ularni filialga bog'lab bo'lmaydi. "
                    "Filiallarni tadbir boshlanishidan oldin belgilang.",
                )
        event.branches = branches
    await db.commit()
    await db.refresh(event)
    queue_service.schedule_event_broadcast(event.id)
    return await _event_out(db, event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[OwnerOnly])
async def delete_event(db: DbSession, event: CompanyEvent) -> None:
    await db.delete(event)
    await db.commit()


@router.get("/{event_id}/state", dependencies=[AnyStaff])
async def event_state(db: DbSession, event: CompanyEvent) -> dict:
    return await queue_service.build_staff_state(db, event)


@router.get("/{event_id}/tickets", response_model=list[TicketOut], dependencies=[AnyStaff])
async def list_tickets(
    db: DbSession,
    event: CompanyEvent,
    q: str | None = None,
    ticket_status: TicketStatus | None = None,
    branch_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[TicketOut]:
    stmt = select(Ticket).where(Ticket.event_id == event.id)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Ticket.first_name.ilike(needle),
                Ticket.last_name.ilike(needle),
                Ticket.phone.ilike(needle),
                Ticket.number.ilike(needle),
            )
        )
    if ticket_status is not None:
        stmt = stmt.where(Ticket.status == ticket_status)
    if branch_id is not None:
        stmt = stmt.where(Ticket.branch_id == branch_id)
    stmt = stmt.order_by(Ticket.registered_at.desc()).limit(min(limit, 500)).offset(offset)
    tickets = (await db.scalars(stmt)).all()
    desk_ids = {t.desk_id for t in tickets if t.desk_id}
    desk_numbers: dict[int, int] = {}
    if desk_ids:
        rows = (await db.execute(select(Desk.id, Desk.number).where(Desk.id.in_(desk_ids)))).all()
        desk_numbers = dict(rows)
    branch_names = {b.id: b.name for b in event.branches}
    out = []
    for t in tickets:
        item = _ticket_out(t, desk_numbers)
        item.branch_name = branch_names.get(t.branch_id) if t.branch_id else None
        out.append(item)
    return out


@router.post("/{event_id}/seed", response_model=list[TicketOut], dependencies=[OwnerOnly])
async def seed_tickets(
    payload: SeedRequest, db: DbSession, event: CompanyEvent
) -> list[TicketOut]:
    """Create fake registered tickets for demos and rehearsals. Branch events
    get the fakes spread round-robin across their branches."""
    import secrets as _secrets

    event_id = event.id
    branch_ids = event.branch_ids()
    made: list[Ticket] = []
    for i in range(payload.count):
        first, last = SEED_NAMES[i % len(SEED_NAMES)]
        phone = f"+9989{_secrets.randbelow(90000000) + 10000000}"
        try:
            ticket = await ticket_service.create_ticket(
                db, event,
                first_name=first, last_name=last, phone=phone,
                branch_id=branch_ids[i % len(branch_ids)] if branch_ids else None,
                source=TicketSource.SEED,
            )
        except Exception:
            continue
        made.append(ticket)
    queue_service.schedule_event_broadcast(event_id)
    return [_ticket_out(t, {}) for t in made]
