import secrets

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SaleEvent, Ticket, TicketSource
from app.services.errors import ConflictError, DomainError

MIN_NUMBER = 1000
MAX_NUMBER = 9999
CAPACITY = MAX_NUMBER - MIN_NUMBER + 1


def make_code(number: int) -> str:
    return f"NVB-{number}-{secrets.token_hex(3).upper()}"


async def _pick_free_number(db: AsyncSession, event_id: int) -> int:
    """Random, non-sequential 4-digit number, unique within the event."""
    for _ in range(40):
        candidate = MIN_NUMBER + secrets.randbelow(CAPACITY)
        taken = await db.scalar(
            select(Ticket.id).where(Ticket.event_id == event_id, Ticket.number == candidate)
        )
        if taken is None:
            return candidate
    # dense event: fall back to choosing uniformly among the remaining numbers
    used = set(
        (await db.scalars(select(Ticket.number).where(Ticket.event_id == event_id))).all()
    )
    free = [n for n in range(MIN_NUMBER, MAX_NUMBER + 1) if n not in used]
    if not free:
        raise DomainError("Tadbirda bo'sh raqam qolmadi (9000 ta chegara)")
    return secrets.choice(free)


async def get_ticket_by_phone(db: AsyncSession, event_id: int, phone: str) -> Ticket | None:
    return await db.scalar(
        select(Ticket).where(Ticket.event_id == event_id, Ticket.phone == phone)
    )


async def get_ticket_by_chat(db: AsyncSession, event_id: int, chat_id: int) -> Ticket | None:
    return await db.scalar(
        select(Ticket).where(
            Ticket.event_id == event_id, Ticket.telegram_chat_id == chat_id
        )
    )


async def create_ticket(
    db: AsyncSession,
    event: SaleEvent,
    *,
    first_name: str,
    last_name: str,
    phone: str,
    telegram_chat_id: int | None = None,
    source: TicketSource = TicketSource.BOT,
) -> Ticket:
    if not event.registration_open():
        raise DomainError("Bu tadbir uchun ro'yxatdan o'tish yopilgan")

    existing = await get_ticket_by_phone(db, event.id, phone)
    if existing is not None:
        raise ConflictError("Bu telefon raqamiga navbat allaqachon berilgan")

    count = await db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.event_id == event.id)
    )
    if count >= CAPACITY:
        raise DomainError("Tadbirda bo'sh raqam qolmadi (9000 ta chegara)")

    for _ in range(5):
        number = await _pick_free_number(db, event.id)
        ticket = Ticket(
            event_id=event.id,
            number=number,
            code=make_code(number),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            telegram_chat_id=telegram_chat_id,
            source=source,
        )
        db.add(ticket)
        try:
            await db.commit()
        except IntegrityError:
            # lost a race for the number (or phone registered concurrently)
            await db.rollback()
            if await get_ticket_by_phone(db, event.id, phone):
                raise ConflictError("Bu telefon raqamiga navbat allaqachon berilgan") from None
            continue
        await db.refresh(ticket)
        return ticket
    raise DomainError("Raqam berishda xatolik — qayta urinib ko'ring")
