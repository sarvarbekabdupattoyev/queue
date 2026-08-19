"""Queue domain logic.

Ordering rule (the product's core): clients get a random 4-letter uppercase
code from the Telegram bot when they register. On the sale day they check in
(QR scan or manual code entry) until ``event.checkin_until``. When that moment
passes the queue starts, and the order among checked-in tickets is the **bot
registration time** — not the code and not the arrival time. Tickets checked
in after the deadline (or returning after a skip) join the end-of-day group.

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
    BotUser,
    Company,
    Desk,
    SaleEvent,
    Ticket,
    TicketStatus,
)
from app.services import i18n, notify
from app.services.broadcast import schedule_event_broadcast
from app.services.errors import ConflictError, DomainError, NotFoundError

TASHKENT = ZoneInfo("Asia/Tashkent")


def fmt_local(dt: datetime) -> str:
    return dt.astimezone(TASHKENT).strftime("%H:%M (%d.%m.%Y)")


def _epoch_us(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000)


# ---------------------------------------------------------------- queries ---

def _waiting_stmt(event_id: int, branch_id: int | None = None):
    stmt = select(Ticket).where(
        Ticket.event_id == event_id, Ticket.status == TicketStatus.CHECKED_IN
    )
    if branch_id is not None:
        stmt = stmt.where(Ticket.branch_id == branch_id)
    return stmt.order_by(Ticket.queue_order, Ticket.id)


async def waiting_tickets(
    db: AsyncSession, event_id: int, branch_id: int | None = None
) -> list[Ticket]:
    return list((await db.scalars(_waiting_stmt(event_id, branch_id))).all())


async def waiting_count(
    db: AsyncSession, event_id: int, branch_id: int | None = None
) -> int:
    stmt = (
        select(func.count())
        .select_from(Ticket)
        .where(Ticket.event_id == event_id, Ticket.status == TicketStatus.CHECKED_IN)
    )
    if branch_id is not None:
        stmt = stmt.where(Ticket.branch_id == branch_id)
    return (await db.scalar(stmt)) or 0


async def active_tickets(
    db: AsyncSession, event_id: int, branch_id: int | None = None
) -> list[Ticket]:
    stmt = (
        select(Ticket)
        .where(
            Ticket.event_id == event_id,
            Ticket.status.in_(TicketStatus.active_desk_statuses()),
        )
        .order_by(Ticket.called_at.desc())
    )
    if branch_id is not None:
        stmt = stmt.where(Ticket.branch_id == branch_id)
    return list((await db.scalars(stmt)).all())


async def position_of(db: AsyncSession, ticket: Ticket) -> int | None:
    """1-based position among the checked-in tickets of the SAME branch
    (branch NULL compares as IS NULL, i.e. the single-office queue)."""
    if ticket.status != TicketStatus.CHECKED_IN:
        return None
    ahead = await db.scalar(
        select(func.count())
        .select_from(Ticket)
        .where(
            Ticket.event_id == ticket.event_id,
            Ticket.branch_id == ticket.branch_id,
            Ticket.status == TicketStatus.CHECKED_IN,
            (Ticket.queue_order < ticket.queue_order)
            | ((Ticket.queue_order == ticket.queue_order) & (Ticket.id < ticket.id)),
        )
    )
    return (ahead or 0) + 1


async def get_ticket_by_number(db: AsyncSession, event_id: int, number: str) -> Ticket:
    ticket = await db.scalar(
        select(Ticket).where(Ticket.event_id == event_id, Ticket.number == number)
    )
    if ticket is None:
        raise NotFoundError("Bunday kodli navbat topilmadi")
    return ticket


async def desk_numbers_for(db: AsyncSession, tickets: list[Ticket]) -> dict[int, int]:
    desk_ids = {t.desk_id for t in tickets if t.desk_id is not None}
    if not desk_ids:
        return {}
    rows = (await db.execute(select(Desk.id, Desk.number).where(Desk.id.in_(desk_ids)))).all()
    return dict(rows)


# ----------------------------------------------------------- state payloads ---

def _stats_from(by_status: dict[TicketStatus, int]) -> dict[str, int]:
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


async def _stats_by_branch(
    db: AsyncSession, event_id: int
) -> tuple[dict[str, int], dict[int, dict[str, int]]]:
    """Overall stats plus a per-branch breakdown in a single grouped query."""
    rows = (
        await db.execute(
            select(Ticket.branch_id, Ticket.status, func.count())
            .where(Ticket.event_id == event_id)
            .group_by(Ticket.branch_id, Ticket.status)
        )
    ).all()
    overall: dict[TicketStatus, int] = {}
    per_branch: dict[int, dict[TicketStatus, int]] = {}
    for branch_id, status, count in rows:
        overall[status] = overall.get(status, 0) + count
        if branch_id is not None:
            per_branch.setdefault(branch_id, {})[status] = count
    return _stats_from(overall), {b: _stats_from(s) for b, s in per_branch.items()}


def _event_info(event: SaleEvent, company: Company | None) -> dict[str, Any]:
    return {
        "id": event.id,
        "name": event.name,
        "phase": event.phase().value,
        "starts_at": event.starts_at.isoformat(),
        "checkin_until": event.checkin_until.isoformat(),
        "company_name": company.name if company else "",
        "logo_url": f"/media/{company.logo_path}" if company and company.logo_path else None,
        "branches": [{"id": b.id, "name": b.name} for b in event.branches],
    }


async def build_states(
    db: AsyncSession, event: SaleEvent
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the public (display) and staff payloads in one query pass.

    Branch events keep ONE payload per event (one broadcast room): every
    ticket entry carries its branch_id and ``by_branch`` holds the per-branch
    queues, so each screen filters down to its own branch client-side.
    """
    company = await db.get(Company, event.company_id)
    branches = list(event.branches)
    branch_names = {b.id: b.name for b in branches}
    waiting = await waiting_tickets(db, event.id)
    active = await active_tickets(db, event.id)
    desk_numbers = await desk_numbers_for(db, active)
    stats, branch_stats = await _stats_by_branch(db, event.id)
    settings = get_settings()

    def queue_entry(t: Ticket) -> dict[str, Any]:
        """What the TV board shows per waiting ticket: the 4-letter code, the
        client's name and the exact bot registration moment (milliseconds —
        it IS the queue order, so the board makes the ordering verifiable)."""
        return {
            "number": t.number,
            "name": t.full_name,
            "registered_at": t.registered_at.isoformat(timespec="milliseconds"),
            "late": t.late,
        }

    def branch_section(branch_id: int) -> dict[str, Any]:
        mine = [t for t in waiting if t.branch_id == branch_id]
        return {
            "id": branch_id,
            "name": branch_names.get(branch_id, ""),
            "next": [queue_entry(t) for t in mine[:12]],
            "stats": branch_stats.get(branch_id, _stats_from({})),
        }

    public_state: dict[str, Any] = {
        "type": "state",
        "event": _event_info(event, company),
        "now": now_utc().isoformat(),
        "call_timeout_minutes": settings.call_timeout_minutes,
        "called": [
            {
                "number": t.number,
                "name": t.full_name,
                "desk_number": desk_numbers.get(t.desk_id),
                "branch_id": t.branch_id,
                "status": t.status.value,
                "called_at": t.called_at.isoformat() if t.called_at else None,
            }
            for t in active
        ],
        "next": [queue_entry(t) for t in waiting[:12]],
        "by_branch": [branch_section(b.id) for b in branches],
        "stats": stats,
    }

    branch_positions: dict[int | None, int] = {}

    def staff_view(t: Ticket, waiting_entry: bool = False) -> dict[str, Any]:
        position = None
        if waiting_entry:
            position = branch_positions.get(t.branch_id, 0) + 1
            branch_positions[t.branch_id] = position
        return {
            "id": t.id,
            "number": t.number,
            "name": t.full_name,
            "phone": t.phone,
            "status": t.status.value,
            "late": t.late,
            "branch_id": t.branch_id,
            "branch_name": branch_names.get(t.branch_id),
            "desk_id": t.desk_id,
            "desk_number": desk_numbers.get(t.desk_id),
            "called_at": t.called_at.isoformat() if t.called_at else None,
            "registered_at": t.registered_at.isoformat(),
            "skip_count": t.skip_count,
            "position": position,
        }

    staff_state: dict[str, Any] = {
        **public_state,
        "waiting_list": [staff_view(t, waiting_entry=True) for t in waiting],
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
    # prefer the bot the client registered through (only that bot is
    # guaranteed to be allowed to message them)
    await notify.send_telegram_text(
        event.company_id, ticket.telegram_chat_id, text, bot_id=ticket.bot_id
    )


async def _ticket_lang(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> str:
    """Language the client chose in the bot (bot_users) — notifications go
    out in it. Tickets without a chat fall back to the default (no send)."""
    if ticket.telegram_chat_id is None:
        return i18n.DEFAULT_LANG
    lang = await db.scalar(
        select(BotUser.language).where(
            BotUser.company_id == event.company_id,
            BotUser.chat_id == ticket.telegram_chat_id,
        )
    )
    return i18n.norm_lang(lang)


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
        lang = await _ticket_lang(db, event, ticket)
        if on_time and not event.queue_started(now):
            message = i18n.t(
                lang,
                "ntf_checkin_prequeue",
                number=ticket.number,
                time=fmt_local(event.checkin_until),
                position=position,
            )
        elif on_time:
            message = i18n.t(
                lang, "ntf_checkin_queue", number=ticket.number, ahead=position - 1
            )
        else:
            message = i18n.t(
                lang, "ntf_checkin_late", number=ticket.number, ahead=position - 1
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
            lang = await _ticket_lang(db, event, ticket)
            await _notify(
                event, ticket, i18n.t(lang, "ntf_cancelled_two_skips", number=ticket.number)
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
        lang = await _ticket_lang(db, event, ticket)
        await _notify(
            event,
            ticket,
            i18n.t(lang, "ntf_rejoined_late", number=ticket.number, ahead=position - 1),
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
    # branch events: a desk serves only its own branch's slice of the queue
    branch_ids = event.branch_ids()
    branch_scope: int | None = None
    if branch_ids:
        if desk.branch_id is None:
            raise DomainError("Bu tadbir filiallarda o'tkaziladi — stolni filialga biriktiring")
        if desk.branch_id not in branch_ids:
            raise DomainError("Bu stol filiali tadbirga qo'shilmagan")
        branch_scope = desk.branch_id
    busy = await db.scalar(
        select(Ticket.id).where(
            Ticket.event_id == event.id,
            Ticket.desk_id == desk.id,
            Ticket.status.in_(TicketStatus.active_desk_statuses()),
        )
    )
    if busy is not None:
        raise ConflictError("Bu stolda hali mijoz bor — avval yakunlang yoki o'tkazib yuboring")

    ticket = await db.scalar(_waiting_stmt(event.id, branch_scope).limit(1))
    if ticket is None:
        return None
    settings = get_settings()
    ticket.status = TicketStatus.CALLED
    ticket.desk_id = desk.id
    ticket.called_at = now_utc()
    ticket.call_count += 1
    await db.commit()
    schedule_event_broadcast(event.id)
    lang = await _ticket_lang(db, event, ticket)
    await _notify(
        event,
        ticket,
        i18n.t(
            lang,
            "ntf_called",
            number=ticket.number,
            desk=desk.number,
            minutes=settings.call_timeout_minutes,
        ),
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
    lang = await _ticket_lang(db, event, ticket)
    await _notify(
        event,
        ticket,
        i18n.t(lang, "ntf_recalled", number=ticket.number, desk=desk.number if desk else "?"),
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
    lang = await _ticket_lang(db, event, ticket)
    key = "ntf_skip_final" if ticket.skip_count >= 2 else "ntf_skip_once"
    await _notify(event, ticket, i18n.t(lang, key))
    return ticket


async def finish(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> Ticket:
    if ticket.status not in TicketStatus.active_desk_statuses():
        raise DomainError("Faqat stoldagi mijozni yakunlash mumkin")
    ticket.status = TicketStatus.DONE
    ticket.finished_at = now_utc()
    await db.commit()
    schedule_event_broadcast(event.id)
    lang = await _ticket_lang(db, event, ticket)
    await _notify(event, ticket, i18n.t(lang, "ntf_done", number=ticket.number))
    return ticket


async def cancel(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> Ticket:
    if ticket.status in (TicketStatus.DONE, TicketStatus.CANCELLED):
        raise DomainError("Bu navbatni bekor qilib bo'lmaydi")
    ticket.status = TicketStatus.CANCELLED
    ticket.desk_id = None
    await db.commit()
    schedule_event_broadcast(event.id)
    lang = await _ticket_lang(db, event, ticket)
    await _notify(event, ticket, i18n.t(lang, "ntf_cancelled_admin", number=ticket.number))
    return ticket
