"""Queue domain logic.

Ordering rule (the product's core): clients get a random 4-digit number from
the Telegram bot when they register. On the sale day they check in (QR scan or
manual number entry) until ``event.checkin_until``. When that moment passes the
queue starts, and the order among checked-in tickets is the **bot registration
time** — not the number and not the arrival time. Tickets checked in after the
deadline (or returning after a skip) join the end-of-day group.

Side effects of every action are decoupled from the request path:
state broadcasts are debounced (`app.services.broadcast`) and Telegram
notifications are routed through `app.services.notify`.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import now_utc
from app.models import (
    LATE_ORDER_BASE,
    Company,
    Desk,
    SaleEvent,
    Ticket,
    TicketStatus,
)
from app.services import notify
from app.services.broadcast import schedule_event_broadcast
from app.services.errors import ConflictError, DomainError, NotFoundError

TASHKENT = ZoneInfo("Asia/Tashkent")


def fmt_local(dt: datetime) -> str:
    return dt.astimezone(TASHKENT).strftime("%H:%M (%d.%m.%Y)")


def _epoch_us(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000)


# ---------------------------------------------------------------- queries ---

def _waiting_stmt(event_id: int):
    return (
        select(Ticket)
        .where(Ticket.event_id == event_id, Ticket.status == TicketStatus.CHECKED_IN)
        .order_by(Ticket.queue_order, Ticket.id)
    )


async def waiting_tickets(db: AsyncSession, event_id: int) -> list[Ticket]:
    return list((await db.scalars(_waiting_stmt(event_id))).all())


async def waiting_count(db: AsyncSession, event_id: int) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.event_id == event_id, Ticket.status == TicketStatus.CHECKED_IN)
        )
    ) or 0


async def active_tickets(db: AsyncSession, event_id: int) -> list[Ticket]:
    stmt = (
        select(Ticket)
        .where(
            Ticket.event_id == event_id,
            Ticket.status.in_(TicketStatus.active_desk_statuses()),
        )
        .order_by(Ticket.called_at.desc())
    )
    return list((await db.scalars(stmt)).all())


async def position_of(db: AsyncSession, ticket: Ticket) -> int | None:
    if ticket.status != TicketStatus.CHECKED_IN:
        return None
    ahead = await db.scalar(
        select(func.count())
        .select_from(Ticket)
        .where(
            Ticket.event_id == ticket.event_id,
            Ticket.status == TicketStatus.CHECKED_IN,
            (Ticket.queue_order < ticket.queue_order)
            | ((Ticket.queue_order == ticket.queue_order) & (Ticket.id < ticket.id)),
        )
    )
    return (ahead or 0) + 1


async def get_ticket_by_number(db: AsyncSession, event_id: int, number: int) -> Ticket:
    ticket = await db.scalar(
        select(Ticket).where(Ticket.event_id == event_id, Ticket.number == number)
    )
    if ticket is None:
        raise NotFoundError("Bunday raqamli navbat topilmadi")
    return ticket


async def desk_numbers_for(db: AsyncSession, tickets: list[Ticket]) -> dict[int, int]:
    desk_ids = {t.desk_id for t in tickets if t.desk_id is not None}
    if not desk_ids:
        return {}
    rows = (await db.execute(select(Desk.id, Desk.number).where(Desk.id.in_(desk_ids)))).all()
    return dict(rows)


# ----------------------------------------------------------- state payloads ---

async def _stats(db: AsyncSession, event_id: int) -> dict[str, int]:
    rows = (
        await db.execute(
            select(Ticket.status, func.count())
            .where(Ticket.event_id == event_id)
            .group_by(Ticket.status)
        )
    ).all()
    by_status = {status: count for status, count in rows}
    total = sum(c for s, c in by_status.items() if s != TicketStatus.CANCELLED)
    arrived = sum(
        c
        for s, c in by_status.items()
        if s not in (TicketStatus.REGISTERED, TicketStatus.CANCELLED)
    )
    return {
        "registered": total,
        "arrived": arrived,
        "waiting": by_status.get(TicketStatus.CHECKED_IN, 0),
        "done": by_status.get(TicketStatus.DONE, 0),
        "skipped": by_status.get(TicketStatus.SKIPPED, 0),
    }


def _event_info(event: SaleEvent, company: Company | None) -> dict[str, Any]:
    return {
        "id": event.id,
        "name": event.name,
        "phase": event.phase().value,
        "starts_at": event.starts_at.isoformat(),
        "checkin_until": event.checkin_until.isoformat(),
        "company_name": company.name if company else "",
        "logo_url": f"/media/{company.logo_path}" if company and company.logo_path else None,
    }


async def build_states(
    db: AsyncSession, event: SaleEvent
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the public (display) and staff payloads in one query pass."""
    company = await db.get(Company, event.company_id)
    waiting = await waiting_tickets(db, event.id)
    active = await active_tickets(db, event.id)
    desk_numbers = await desk_numbers_for(db, active)
    stats = await _stats(db, event.id)
    settings = get_settings()

    public_state: dict[str, Any] = {
        "type": "state",
        "event": _event_info(event, company),
        "now": now_utc().isoformat(),
        "call_timeout_minutes": settings.call_timeout_minutes,
        "called": [
            {
                "number": t.number,
                "desk_number": desk_numbers.get(t.desk_id),
                "status": t.status.value,
                "called_at": t.called_at.isoformat() if t.called_at else None,
            }
            for t in active
        ],
        "next": [t.number for t in waiting[:12]],
        "late_numbers": [t.number for t in waiting[:12] if t.late],
        "stats": stats,
    }

    def staff_view(t: Ticket, position: int | None = None) -> dict[str, Any]:
        return {
            "id": t.id,
            "number": t.number,
            "name": t.full_name,
            "phone": t.phone,
            "status": t.status.value,
            "late": t.late,
            "desk_id": t.desk_id,
            "desk_number": desk_numbers.get(t.desk_id),
            "called_at": t.called_at.isoformat() if t.called_at else None,
            "registered_at": t.registered_at.isoformat(),
            "skip_count": t.skip_count,
            "position": position,
        }

    staff_state: dict[str, Any] = {
        **public_state,
        "waiting_list": [staff_view(t, i + 1) for i, t in enumerate(waiting)],
        "active": [staff_view(t) for t in active],
    }
    return public_state, staff_state


async def build_public_state(db: AsyncSession, event: SaleEvent) -> dict[str, Any]:
    public_state, _ = await build_states(db, event)
    return public_state


async def build_staff_state(db: AsyncSession, event: SaleEvent) -> dict[str, Any]:
    _, staff_state = await build_states(db, event)
    return staff_state


# ----------------------------------------------------------- notifications ---

async def _notify(event: SaleEvent, ticket: Ticket, text: str) -> None:
    if ticket.telegram_chat_id is None:
        return
    await notify.send_telegram_text(event.company_id, ticket.telegram_chat_id, text)


# ----------------------------------------------------------------- actions ---

async def check_in(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> dict[str, Any]:
    """QR scanned or number entered at the reception."""
    if not event.is_active:
        raise DomainError("Tadbir yopilgan")
    now = now_utc()

    if ticket.status == TicketStatus.REGISTERED:
        on_time = now < event.checkin_until
        if on_time:
            ticket.late = False
            ticket.queue_order = _epoch_us(ticket.registered_at)
        else:
            event.late_seq += 1
            ticket.late = True
            ticket.queue_order = LATE_ORDER_BASE + event.late_seq
        ticket.status = TicketStatus.CHECKED_IN
        ticket.checked_in_at = now
        await db.commit()
        position = await position_of(db, ticket)
        if on_time and not event.queue_started(now):
            message = (
                f"✅ Kelganingiz qayd etildi (№{ticket.number}).\n"
                f"Navbat {fmt_local(event.checkin_until)} da boshlanadi. Tartib botdan "
                f"ro'yxatdan o'tgan vaqt bo'yicha belgilanadi — hozircha siz {position}-o'rindasiz."
            )
        elif on_time:
            message = (
                f"✅ Kelganingiz qayd etildi (№{ticket.number}). Navbatingizni kuting — "
                f"sizdan oldin {position - 1} kishi bor. Chaqirilganingizda xabar keladi."
            )
        else:
            message = (
                f"✅ Qayd etildi (№{ticket.number}). Skanerlash vaqti tugagani uchun kun "
                f"oxiri navbatiga qo'shildingiz — sizdan oldin {position - 1} kishi bor."
            )
        schedule_event_broadcast(event.id)
        await _notify(event, ticket, message)
        kind = "late" if ticket.late else "arrived"
        return {"ok": True, "kind": kind, "message": "Keldi belgilandi", "ticket": ticket}

    if ticket.status == TicketStatus.SKIPPED:
        if ticket.skip_count >= 2:
            ticket.status = TicketStatus.CANCELLED
            await db.commit()
            schedule_event_broadcast(event.id)
            await _notify(
                event,
                ticket,
                f"Navbatingiz (№{ticket.number}) bekor qilindi: ikki marta chaqiruvda bo'lmadingiz.",
            )
            return {
                "ok": False,
                "kind": "cancelled",
                "message": "Ikki marta o'tkazib yuborilgan — navbat bekor qilindi",
                "ticket": ticket,
            }
        event.late_seq += 1
        ticket.late = True
        ticket.queue_order = LATE_ORDER_BASE + event.late_seq
        ticket.status = TicketStatus.CHECKED_IN
        ticket.checked_in_at = now
        await db.commit()
        position = await position_of(db, ticket)
        schedule_event_broadcast(event.id)
        await _notify(
            event,
            ticket,
            f"↩️ Kun oxiri navbatiga qo'shildingiz (№{ticket.number}). "
            f"Sizdan oldin {position - 1} kishi bor.",
        )
        return {"ok": True, "kind": "late", "message": "Kun oxiri navbatiga qo'shildi", "ticket": ticket}

    if ticket.status == TicketStatus.CHECKED_IN:
        position = await position_of(db, ticket)
        return {
            "ok": False,
            "kind": "already",
            "message": f"Allaqachon belgilangan (navbatda {position}-o'rinda)",
            "ticket": ticket,
        }
    if ticket.status == TicketStatus.CALLED:
        desk = await db.get(Desk, ticket.desk_id) if ticket.desk_id else None
        desk_number = desk.number if desk else "?"
        return {
            "ok": False,
            "kind": "called",
            "message": f"Chaqirilgan — {desk_number}-stolga borsin",
            "ticket": ticket,
        }
    if ticket.status == TicketStatus.SERVING:
        return {"ok": False, "kind": "serving", "message": "Hozir xizmat ko'rsatilmoqda", "ticket": ticket}
    if ticket.status == TicketStatus.DONE:
        return {"ok": False, "kind": "done", "message": "Xizmat allaqachon yakunlangan", "ticket": ticket}
    return {"ok": False, "kind": "cancelled", "message": "Bu navbat bekor qilingan", "ticket": ticket}


async def call_next(db: AsyncSession, event: SaleEvent, desk: Desk) -> Ticket | None:
    if not event.is_active:
        raise DomainError("Tadbir yopilgan")
    if not event.queue_started():
        raise DomainError(
            f"Navbat hali boshlanmagan — skanerlash {fmt_local(event.checkin_until)} gacha davom etadi"
        )
    busy = await db.scalar(
        select(Ticket.id).where(
            Ticket.event_id == event.id,
            Ticket.desk_id == desk.id,
            Ticket.status.in_(TicketStatus.active_desk_statuses()),
        )
    )
    if busy is not None:
        raise ConflictError("Bu stolda hali mijoz bor — avval yakunlang yoki o'tkazib yuboring")

    ticket = await db.scalar(_waiting_stmt(event.id).limit(1))
    if ticket is None:
        return None
    settings = get_settings()
    ticket.status = TicketStatus.CALLED
    ticket.desk_id = desk.id
    ticket.called_at = now_utc()
    ticket.call_count += 1
    await db.commit()
    schedule_event_broadcast(event.id)
    await _notify(
        event,
        ticket,
        f"🔔 Sizning navbatingiz! №{ticket.number} — {desk.number}-stolga yaqinlashing.\n"
        f"{settings.call_timeout_minutes} daqiqa ichida kelmasangiz o'tkazib yuborilasiz.",
    )
    return ticket


async def recall(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> Ticket:
    if ticket.status != TicketStatus.CALLED:
        raise DomainError("Faqat chaqirilgan mijozni qayta chaqirish mumkin")
    desk = await db.get(Desk, ticket.desk_id) if ticket.desk_id else None
    ticket.called_at = now_utc()
    ticket.call_count += 1
    await db.commit()
    schedule_event_broadcast(event.id)
    desk_number = desk.number if desk else "?"
    await _notify(
        event,
        ticket,
        f"🔔🔔 Takroriy chaqiruv: №{ticket.number} — {desk_number}-stolga yaqinlashing!",
    )
    return ticket


async def start_serving(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> Ticket:
    if ticket.status != TicketStatus.CALLED:
        raise DomainError("Faqat chaqirilgan mijozni qabul qilish mumkin")
    ticket.status = TicketStatus.SERVING
    await db.commit()
    schedule_event_broadcast(event.id)
    return ticket


async def skip(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> Ticket:
    if ticket.status != TicketStatus.CALLED:
        raise DomainError("Faqat chaqirilgan mijozni o'tkazib yuborish mumkin")
    ticket.status = TicketStatus.SKIPPED
    ticket.skip_count += 1
    ticket.desk_id = None
    await db.commit()
    schedule_event_broadcast(event.id)
    if ticket.skip_count >= 2:
        text = (
            "⏭ Chaqiruvda yana bo'lmadingiz. Kun oxiri navbati faqat bir marta beriladi — "
            "qabulxonaga murojaat qiling."
        )
    else:
        text = (
            "⏭ Afsuski, chaqiruvda bo'lmadingiz va o'tkazib yuborildingiz. Ofisda bo'lsangiz, "
            "qabulxonada QR-kodingizni qayta ko'rsating — kun oxiri navbatiga qo'shamiz (bir marta)."
        )
    await _notify(event, ticket, text)
    return ticket


async def finish(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> Ticket:
    if ticket.status not in TicketStatus.active_desk_statuses():
        raise DomainError("Faqat stoldagi mijozni yakunlash mumkin")
    ticket.status = TicketStatus.DONE
    ticket.finished_at = now_utc()
    await db.commit()
    schedule_event_broadcast(event.id)
    await _notify(
        event,
        ticket,
        f"🎉 Rahmat! Xizmat yakunlandi (№{ticket.number}). Yaxshi kun tilaymiz.",
    )
    return ticket


async def cancel(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> Ticket:
    if ticket.status in (TicketStatus.DONE, TicketStatus.CANCELLED):
        raise DomainError("Bu navbatni bekor qilib bo'lmaydi")
    ticket.status = TicketStatus.CANCELLED
    ticket.desk_id = None
    await db.commit()
    schedule_event_broadcast(event.id)
    await _notify(event, ticket, f"Navbatingiz (№{ticket.number}) administrator tomonidan bekor qilindi.")
    return ticket
