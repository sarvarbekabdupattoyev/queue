import secrets

from sqlalchemy import select
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
    branch_id: int | None = None,
    bot_id: int | None = None,
    source: TicketSource = TicketSource.BOT,
) -> Ticket:
    if not event.registration_open():
        raise DomainError("Bu tadbir uchun ro'yxatdan o'tish yopilgan")
    # A rollback below expires `event`'s loaded attributes; touching event.id
    # afterwards would lazy-load synchronously and crash under asyncpg, so
    # capture it up front and never dereference the ORM object again.
    event_id = event.id
    event_branch_ids = event.branch_ids()
    if event_branch_ids:
        # the client queues at ONE branch of a multi-branch event
        if branch_id not in event_branch_ids:
            raise DomainError("Filial tanlanmagan yoki bu tadbirga tegishli emas")
    else:
        branch_id = None

    existing = await get_ticket_by_phone(db, event_id, phone)
    if existing is not None:
        raise ConflictError("Bu telefon raqamiga navbat allaqachon berilgan")

    # No COUNT pre-check per registration: capacity exhaustion is detected by
    # _pick_free_number's fallback scan, keeping the hot path at 2 SELECTs.
    for _ in range(5):
        number = await _pick_free_number(db, event_id)
        ticket = Ticket(
            event_id=event_id,
            branch_id=branch_id,
            bot_id=bot_id,
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
            # the rollback expired `event`'s attributes — re-hydrate the same
            # identity-mapped instance so callers can keep using their reference
            await db.get(SaleEvent, event_id)
            if await get_ticket_by_phone(db, event_id, phone):
                raise ConflictError("Bu telefon raqamiga navbat allaqachon berilgan") from None
            continue
        # expire_on_commit=False keeps attributes loaded — no refresh needed
        return ticket
    raise DomainError("Raqam berishda xatolik — qayta urinib ko'ring")
