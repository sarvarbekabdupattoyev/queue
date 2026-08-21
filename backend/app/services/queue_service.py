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

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
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
    TicketSource,
    TicketStatus,
)
from app.services import i18n, notify, ticket_service
from app.services.broadcast import schedule_event_broadcast
from app.services.errors import ConflictError, DomainError, NotFoundError

log = logging.getLogger(__name__)

TASHKENT = ZoneInfo("Asia/Tashkent")


def fmt_local(dt: datetime) -> str:
    return dt.astimezone(TASHKENT).strftime("%H:%M (%d.%m.%Y)")


def fmt_local_ms(dt: datetime) -> str:
    """Registration moments carry milliseconds — they ARE the queue order."""
    local = dt.astimezone(TASHKENT)
    return local.strftime("%H:%M:%S") + f".{local.microsecond // 1000:03d}" + local.strftime(" (%d.%m.%Y)")


def _epoch_us(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000)


async def _next_late_seq(db: AsyncSession, event_id: int) -> int:
    """Reserve the next end-of-day slot atomically (safe across workers)."""
    return (
        await db.execute(
            update(SaleEvent)
            .where(SaleEvent.id == event_id)
            .values(late_seq=SaleEvent.late_seq + 1)
            .returning(SaleEvent.late_seq)
            .execution_options(synchronize_session=False)
        )
    ).scalar_one()


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

# Sale-outcome counters (contract signed / not signed) are business figures —
# they belong to staff screens only and never reach the public TV payload.
STAFF_ONLY_STATS = ("contracts", "no_contract")


class _Tally:
    """Mutable per-scope counters: by status, plus the admin metrics the
    product tracks separately — late comers, staff-added walk-ins and the
    sale outcome (contract signed or not) of finished clients."""

    def __init__(self) -> None:
        self.by_status: dict[TicketStatus, int] = {}
        self.late = 0
        self.staff_added = 0
        self.contracts = 0
        self.no_contract = 0

    def add(
        self,
        status: TicketStatus,
        late: bool,
        source: TicketSource,
        contract_signed: bool | None,
        count: int,
    ) -> None:
        self.by_status[status] = self.by_status.get(status, 0) + count
        if late:
            self.late += count
        if source == TicketSource.STAFF:
            self.staff_added += count
        # the outcome is only meaningful on finished clients; NULL = the
        # question was never answered (e.g. tickets finished before the
        # feature existed) and counts in neither bucket
        if status == TicketStatus.DONE and contract_signed is not None:
            if contract_signed:
                self.contracts += count
            else:
                self.no_contract += count


def _stats_from(tally: "_Tally | None" = None) -> dict[str, int]:
    tally = tally or _Tally()
    by_status = tally.by_status
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
        "late": tally.late,
        "staff_added": tally.staff_added,
        "contracts": tally.contracts,
        "no_contract": tally.no_contract,
    }


async def _stats_by_branch(
    db: AsyncSession, event_id: int
) -> tuple[dict[str, int], dict[int, dict[str, int]]]:
    """Overall stats plus a per-branch breakdown in a single grouped query."""
    rows = (
        await db.execute(
            select(
                Ticket.branch_id,
                Ticket.status,
                Ticket.late,
                Ticket.source,
                Ticket.contract_signed,
                func.count(),
            )
            .where(Ticket.event_id == event_id)
            .group_by(
                Ticket.branch_id,
                Ticket.status,
                Ticket.late,
                Ticket.source,
                Ticket.contract_signed,
            )
        )
    ).all()
    overall = _Tally()
    per_branch: dict[int, _Tally] = {}
    for branch_id, status, late, source, contract_signed, count in rows:
        overall.add(status, late, source, contract_signed, count)
        if branch_id is not None:
            per_branch.setdefault(branch_id, _Tally()).add(
                status, late, source, contract_signed, count
            )
    return _stats_from(overall), {b: _stats_from(t) for b, t in per_branch.items()}


def _event_info(event: SaleEvent, company: Company | None) -> dict[str, Any]:
    return {
        "id": event.id,
        "name": event.name,
        "phase": event.phase().value,
        "registration_starts_at": event.registration_starts_at.isoformat(),
        "starts_at": event.starts_at.isoformat(),
        "checkin_until": event.checkin_until.isoformat(),
        "sale_starts_at": event.sale_starts_at.isoformat(),
        "sale_hold": event.sale_hold,
        "sale_ended_at": event.sale_ended_at.isoformat() if event.sale_ended_at else None,
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
            "stats": branch_stats.get(branch_id, _stats_from()),
        }

    def public_stats(values: dict[str, int]) -> dict[str, int]:
        """The TV board exposes the minimum — sale outcomes stay staff-only."""
        return {k: v for k, v in values.items() if k not in STAFF_ONLY_STATS}

    staff_by_branch = [branch_section(b.id) for b in branches]
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
        "by_branch": [{**s, "stats": public_stats(s["stats"])} for s in staff_by_branch],
        "stats": public_stats(stats),
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
        "stats": stats,
        "by_branch": staff_by_branch,
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

async def _claim_status(
    db: AsyncSession, ticket: Ticket, expected: TicketStatus, **values: Any
) -> bool:
    """Move a ticket out of ``expected`` atomically. Two concurrent scans of
    the same QR race here — exactly one wins; the loser sees the new status
    after the refresh and reports the QR as already used."""
    claimed = (
        await db.execute(
            update(Ticket)
            .where(Ticket.id == ticket.id, Ticket.status == expected)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
    ).rowcount
    await db.commit()
    await db.refresh(ticket)
    return claimed == 1


async def check_in(db: AsyncSession, event: SaleEvent, ticket: Ticket) -> dict[str, Any]:
    """QR scanned or code entered at the reception.

    A QR is single-use: once the ticket left REGISTERED (scanned, or added by
    staff), every further scan is refused without touching the queue.
    """
    if not event.is_active:
        raise DomainError("Tadbir yopilgan")
    if event.sale_ended_at is not None:
        raise DomainError("Sotuv yakunlangan — yangi belgilash qabul qilinmaydi")
    now = now_utc()
    event_id = event.id

    if ticket.status == TicketStatus.REGISTERED:
        # on time = scanned inside the QR window; later scans join the
        # end-of-day group (registration itself is gated at creation time)
        on_time = event.on_time_checkin(now)
        if on_time:
            values: dict[str, Any] = {"late": False, "queue_order": _epoch_us(ticket.registered_at)}
        else:
            values = {"late": True, "queue_order": LATE_ORDER_BASE + await _next_late_seq(db, event_id)}
        claimed = await _claim_status(
            db,
            ticket,
            TicketStatus.REGISTERED,
            status=TicketStatus.CHECKED_IN,
            checked_in_at=now,
            **values,
        )
        if claimed:
            lang = await _ticket_lang(db, event, ticket)
            if not event.queue_started(now):
                # the sale has not started: the final order is not announced yet
                key = "ntf_checkin_prequeue" if on_time else "ntf_checkin_late_prequeue"
                message = i18n.t(
                    lang, key, number=ticket.number, time=fmt_local(event.sale_starts_at)
                )
            else:
                position = await position_of(db, ticket)
                message = i18n.t(
                    lang, "ntf_checkin_late", number=ticket.number, ahead=position - 1
                )
            schedule_event_broadcast(event_id)
            await _notify(event, ticket, message)
            kind = "late" if ticket.late else "arrived"
            return {"ok": True, "kind": kind, "message": "Keldi belgilandi", "ticket": ticket}
        # lost the race: the QR was used a moment ago — fall through and
        # answer from the ticket's real (refreshed) status below

    if ticket.status == TicketStatus.SKIPPED:
        if ticket.skip_count >= 2:
            if not await _claim_status(
                db, ticket, TicketStatus.SKIPPED, status=TicketStatus.CANCELLED
            ):
                return await check_in(db, event, ticket)
            schedule_event_broadcast(event_id)
            lang = await _ticket_lang(db, event, ticket)
            await _notify(
                event, ticket, i18n.t(lang, "ntf_cancelled_two_skips", number=ticket.number)
            )
            await _maybe_end_sale(db, event)
            return {
                "ok": False,
                "kind": "cancelled",
                "message": "Ikki marta o'tkazib yuborilgan — navbat bekor qilindi",
                "ticket": ticket,
            }
        seq = await _next_late_seq(db, event_id)
        if not await _claim_status(
            db,
            ticket,
            TicketStatus.SKIPPED,
            status=TicketStatus.CHECKED_IN,
            checked_in_at=now,
            late=True,
            queue_order=LATE_ORDER_BASE + seq,
        ):
            return await check_in(db, event, ticket)
        position = await position_of(db, ticket)
        schedule_event_broadcast(event_id)
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
            "message": f"QR allaqachon ishlatilgan — navbatda {position}-o'rinda",
            "ticket": ticket,
        }
    if ticket.status == TicketStatus.CALLED:
        desk = await db.get(Desk, ticket.desk_id) if ticket.desk_id else None
        desk_number = desk.number if desk else "?"
        return {
            "ok": False,
            "kind": "called",
            "message": f"QR ishlatilgan, mijoz chaqirilgan — {desk_number}-stolga borsin",
            "ticket": ticket,
        }
    if ticket.status == TicketStatus.SERVING:
        return {"ok": False, "kind": "serving", "message": "QR ishlatilgan — hozir xizmat ko'rsatilmoqda", "ticket": ticket}
    if ticket.status == TicketStatus.DONE:
        return {"ok": False, "kind": "done", "message": "QR ishlatilgan — xizmat allaqachon yakunlangan", "ticket": ticket}
    return {"ok": False, "kind": "cancelled", "message": "Bu navbat bekor qilingan", "ticket": ticket}


async def call_next(db: AsyncSession, event: SaleEvent, desk: Desk) -> Ticket | None:
    if not event.is_active:
        raise DomainError("Tadbir yopilgan")
    if event.sale_ended_at is not None:
        raise DomainError("Sotuv yakunlangan")
    if not event.queue_started():
        raise DomainError(
            f"Sotuv hali boshlanmagan — {fmt_local(event.sale_starts_at)} da boshlanadi"
        )
    if event.sale_hold:
        raise DomainError("Sotuv to'xtatib turilgan — davom ettirilgach chaqiruv ochiladi")
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

    settings = get_settings()
    while True:
        ticket = await db.scalar(_waiting_stmt(event.id, branch_scope).limit(1))
        if ticket is None:
            return None
        # Two desks calling next at once can both select the same waiting
        # ticket — claim it the same way check_in claims a QR scan (atomic
        # conditional UPDATE, not a plain attribute assignment) so only one
        # desk wins; the other simply moves on to the next ticket in line
        # instead of silently overwriting the winner's desk assignment.
        won = await _claim_status(
            db,
            ticket,
            TicketStatus.CHECKED_IN,
            status=TicketStatus.CALLED,
            desk_id=desk.id,
            called_at=now_utc(),
            call_count=Ticket.call_count + 1,
        )
        if won:
            break
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


async def finish(
    db: AsyncSession,
    event: SaleEvent,
    ticket: Ticket,
    contract_signed: bool | None = None,
) -> Ticket:
    if ticket.status not in TicketStatus.active_desk_statuses():
        raise DomainError("Faqat stoldagi mijozni yakunlash mumkin")
    ticket.status = TicketStatus.DONE
    # the manager's answer to "was a contract signed?" — the sale outcome
    ticket.contract_signed = contract_signed
    ticket.finished_at = now_utc()
    await db.commit()
    await _maybe_end_sale(db, event)
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
    await _maybe_end_sale(db, event)
    schedule_event_broadcast(event.id)
    lang = await _ticket_lang(db, event, ticket)
    await _notify(event, ticket, i18n.t(lang, "ntf_cancelled_admin", number=ticket.number))
    return ticket


async def _maybe_end_sale(db: AsyncSession, event: SaleEvent) -> None:
    """The sale ends by itself once every queued client has been handled —
    nobody waiting, nobody at a desk. Skipped clients keep their one comeback
    chance only while the sale runs; the owner can always reopen."""
    if not event.queue_started() or event.sale_hold:
        return
    remaining = await db.scalar(
        select(func.count())
        .select_from(Ticket)
        .where(
            Ticket.event_id == event.id,
            Ticket.status.in_(
                (TicketStatus.CHECKED_IN, TicketStatus.CALLED, TicketStatus.SERVING)
            ),
        )
    )
    if remaining:
        return
    event.sale_ended_at = now_utc()
    await db.commit()
    log.info("Sale for event %s ended automatically — queue drained", event.id)


async def staff_add_ticket(
    db: AsyncSession,
    event: SaleEvent,
    *,
    first_name: str,
    last_name: str,
    phone: str,
    branch_id: int | None,
) -> Ticket:
    """Walk-in client added at the door by the owner or scanner: gets a code
    and QR like everyone else and goes straight to the END of the queue."""
    if event.sale_ended_at is not None:
        raise DomainError("Sotuv yakunlangan — yangi mijoz qo'shib bo'lmaydi")
    event_id = event.id
    ticket = await ticket_service.create_ticket(
        db,
        event,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        branch_id=branch_id,
        source=TicketSource.STAFF,
    )
    ticket.status = TicketStatus.CHECKED_IN
    ticket.checked_in_at = now_utc()
    ticket.late = True
    ticket.queue_order = LATE_ORDER_BASE + await _next_late_seq(db, event_id)
    await db.commit()
    schedule_event_broadcast(event_id)
    return ticket


# ------------------------------------------------------- sale-start burst ---

async def claim_sale_notification(db: AsyncSession, event_id: int) -> bool:
    """Atomically claim the one-time sale-start burst for an event, so N API
    workers running the watcher never notify the same clients twice."""
    claimed = (
        await db.execute(
            update(SaleEvent)
            .where(SaleEvent.id == event_id, SaleEvent.sale_notified.is_(False))
            .values(sale_notified=True)
            .execution_options(synchronize_session=False)
        )
    ).rowcount
    await db.commit()
    return claimed == 1


async def notify_sale_started(db: AsyncSession, event: SaleEvent) -> int:
    """Tell every checked-in client their code, their bot registration moment
    (with milliseconds — it IS the queue order) and how many people are ahead
    of them in their branch's queue. Returns the number of messages queued."""
    waiting = await waiting_tickets(db, event.id)
    chat_ids = [t.telegram_chat_id for t in waiting if t.telegram_chat_id is not None]
    langs: dict[int, str] = {}
    if chat_ids:
        rows = (
            await db.execute(
                select(BotUser.chat_id, BotUser.language).where(
                    BotUser.company_id == event.company_id,
                    BotUser.chat_id.in_(chat_ids),
                )
            )
        ).all()
        langs = dict(rows)
    positions: dict[int | None, int] = {}
    sent = 0
    for t in waiting:
        position = positions.get(t.branch_id, 0) + 1
        positions[t.branch_id] = position
        if t.telegram_chat_id is None:
            continue
        lang = i18n.norm_lang(langs.get(t.telegram_chat_id))
        await notify.send_telegram_text(
            event.company_id,
            t.telegram_chat_id,
            i18n.t(
                lang,
                "ntf_sale_started",
                number=t.number,
                reg_time=fmt_local_ms(t.registered_at),
                ahead=position - 1,
            ),
            bot_id=t.bot_id,
        )
        sent += 1
    return sent
