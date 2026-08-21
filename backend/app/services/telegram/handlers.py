"""Telegram bot conversation, shared by every company bot.

/start → choose language (first time; inline buttons uz/ru/en) → (choose
event if several are open) → (choose branch if the event runs in several) →
F.I.Sh. in one line → phone via the contact button ONLY (typed numbers are
rejected; one phone = one ticket, duplicates get their existing ticket back)
→ ticket with a random 4-letter uppercase code + QR photo.

Registration is gated by ``event.registration_starts_at``: before that
moment the bot registers nobody — /start answers with a "sale has not
started" card instead (when registration opens, how the queue will form,
company locations and call-center numbers).

The persistent menu always carries the company-info button (name, logo,
locations, upcoming sale dates, contact phones) and a language switcher.

Handlers are module-level functions; the owning company and the bot's DB row
are injected by the dispatcher (``Dispatcher(company_id=..., bot_db_id=...)``
workflow data), so N bots — including several parallel bots of ONE company —
share one code path, one FSM storage (keys are bot-scoped) and no closures.
"""

import asyncio
import json
import html
import logging
import re
from contextlib import suppress
from typing import NamedTuple

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.phone import normalize_phone, pretty_phone
from app.core.redis import get_redis
from app.db.base import now_utc
from app.db.session import SessionFactory
from app.models import Branch, BotUser, Company, SaleEvent, Ticket, TicketStatus
from app.services import queue_service, ticket_service
from app.services.errors import DomainError
from app.services.i18n import (
    LANGS,
    LANGUAGE_NAMES,
    LANGUAGE_PROMPT,
    norm_lang,
    status_label,
    t,
)
from app.services.qr_service import qr_png_bytes_async

log = logging.getLogger(__name__)

NAME_WORD_RE = re.compile(r"^[A-Za-zА-Яа-яЎўҚқҒғҲҳXxOoʻʼ'’‘\-]{2,30}$")

# logo formats Telegram accepts as a photo (SVG is skipped)
PHOTO_LOGO_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

# menu buttons match in every language (the keyboard keeps the labels of the
# language it was sent with, even after the user switches)
BTN_TICKET_ALL = {t(lang, "btn_ticket") for lang in LANGS}
BTN_STATUS_ALL = {t(lang, "btn_status") for lang in LANGS}
BTN_INFO_ALL = {t(lang, "btn_info") for lang in LANGS}
BTN_LANG_ALL = {t(lang, "btn_language") for lang in LANGS}

DEAD_LETTER_KEY = "navbat:dead-letter:registrations"
_REGISTRATION_RETRY_ATTEMPTS = 3
_REGISTRATION_RETRY_BASE_DELAY = 0.5  # seconds; multiplied by attempt number


class Registration(StatesGroup):
    choosing_language = State()
    choosing_event = State()
    choosing_branch = State()
    full_name = State()
    phone = State()


def main_menu(lang: str, registered: bool = True) -> ReplyKeyboardMarkup:
    """The ticket/status buttons only exist for chats that hold a ticket —
    an unregistered user sees just the info and language buttons."""
    rows: list[list[KeyboardButton]] = []
    if registered:
        rows.append(
            [KeyboardButton(text=t(lang, "btn_ticket")), KeyboardButton(text=t(lang, "btn_status"))]
        )
    rows.append(
        [KeyboardButton(text=t(lang, "btn_info")), KeyboardButton(text=t(lang, "btn_language"))]
    )
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=LANGUAGE_NAMES[lang], callback_data=f"lang:{lang}")
                for lang in LANGS
            ]
        ]
    )


def phone_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_share_phone"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def split_full_name(text: str) -> tuple[str, str] | None:
    """One-line F.I.Sh. → (first_name, rest). 2–5 letter-only words; the
    first word is the given name, the rest (surname + patronymic) is stored
    as the last name."""
    words = text.strip().split()
    if not 2 <= len(words) <= 5:
        return None
    if any(not NAME_WORD_RE.fullmatch(word) for word in words):
        return None
    first = _cap(words[0])
    rest = " ".join(_cap(word) for word in words[1:])
    if len(first) > 64 or len(rest) > 64:
        return None
    return first, rest


def _cap(value: str) -> str:
    value = value.strip()
    return value[:1].upper() + value[1:] if value else value


# --------------------------------------------------------------- language ---

async def _stored_lang(session: AsyncSession, company_id: int, chat_id: int) -> str | None:
    return await session.scalar(
        select(BotUser.language).where(
            BotUser.company_id == company_id, BotUser.chat_id == chat_id
        )
    )


async def _save_lang(session: AsyncSession, company_id: int, chat_id: int, lang: str) -> None:
    row = await session.scalar(
        select(BotUser).where(BotUser.company_id == company_id, BotUser.chat_id == chat_id)
    )
    if row is not None:
        row.language = lang
        await session.commit()
        return
    session.add(BotUser(company_id=company_id, chat_id=chat_id, language=lang))
    try:
        await session.commit()
    except IntegrityError:
        # two parallel /starts raced on the unique (company, chat) row
        await session.rollback()
        row = await session.scalar(
            select(BotUser).where(BotUser.company_id == company_id, BotUser.chat_id == chat_id)
        )
        if row is not None:
            row.language = lang
            await session.commit()


async def _menu_lang(session: AsyncSession, company_id: int, chat_id: int) -> str:
    return norm_lang(await _stored_lang(session, company_id, chat_id))


# ---------------------------------------------------------------- queries ---

async def _live_events(session: AsyncSession, company_id: int) -> list[SaleEvent]:
    """Active events whose sale has not ended — announced and open alike."""
    events = (
        await session.scalars(
            select(SaleEvent)
            .where(SaleEvent.company_id == company_id, SaleEvent.is_active.is_(True))
            .order_by(SaleEvent.starts_at)
        )
    ).all()
    return [e for e in events if e.sale_ended_at is None]


async def _open_events(session: AsyncSession, company_id: int) -> list[SaleEvent]:
    """Events the bot may register clients for right now."""
    now = now_utc()
    return [e for e in await _live_events(session, company_id) if e.registration_open(now)]


async def _pending_events(session: AsyncSession, company_id: int) -> list[SaleEvent]:
    """Announced events whose registration has not opened yet."""
    now = now_utc()
    return [e for e in await _live_events(session, company_id) if e.registration_pending(now)]


async def _my_tickets(session: AsyncSession, company_id: int, chat_id: int) -> list[Ticket]:
    stmt = (
        select(Ticket)
        .join(SaleEvent, Ticket.event_id == SaleEvent.id)
        .where(
            SaleEvent.company_id == company_id,
            SaleEvent.is_active.is_(True),
            Ticket.telegram_chat_id == chat_id,
            Ticket.status != TicketStatus.CANCELLED,
        )
        .order_by(SaleEvent.starts_at)
    )
    return list((await session.scalars(stmt)).all())


async def _is_registered(session: AsyncSession, company_id: int, chat_id: int) -> bool:
    row = await session.scalar(
        select(Ticket.id)
        .join(SaleEvent, Ticket.event_id == SaleEvent.id)
        .where(
            SaleEvent.company_id == company_id,
            SaleEvent.is_active.is_(True),
            Ticket.telegram_chat_id == chat_id,
            Ticket.status != TicketStatus.CANCELLED,
        )
        .limit(1)
    )
    return row is not None


async def _menu_for(
    session: AsyncSession, company_id: int, chat_id: int, lang: str
) -> ReplyKeyboardMarkup:
    return main_menu(lang, registered=await _is_registered(session, company_id, chat_id))


class TicketMessage(NamedTuple):
    """Everything needed to send a ticket, read from the database up front.

    Sending it means a QR render plus an upload that the per-bot rate limiter
    may hold back for seconds (longer under flood control). Doing that inside
    an open session pins a pooled connection for the whole wait, which is what
    exhausts the pool during a registration burst — so the DB half stops here
    and the delivery happens after the session is closed.
    """

    caption: str
    code: str
    number: str


async def _ticket_message(
    session: AsyncSession, ticket: Ticket, lang: str, intro: str = ""
) -> TicketMessage:
    event = await session.get(SaleEvent, ticket.event_id)
    branch = await session.get(Branch, ticket.branch_id) if ticket.branch_id else None
    branch_line = ""
    if branch is not None:
        # the address tells the client where to actually show up
        where = f"{branch.name} ({branch.address})" if branch.address else branch.name
        branch_line = t(lang, "branch_line", branch=where) + "\n"
    caption = t(
        lang,
        "ticket_caption",
        intro=intro,
        number=ticket.number,
        event=event.name,
        starts=queue_service.fmt_local(event.starts_at),
        branch_line=branch_line,
        name=ticket.full_name,
        phone=pretty_phone(ticket.phone),
        # milliseconds included: this moment IS the client's queue order
        reg_time=queue_service.fmt_local_ms(ticket.registered_at),
        deadline=queue_service.fmt_local(event.checkin_until),
        status=status_label(lang, ticket.status),
    )
    return TicketMessage(caption=caption, code=ticket.code, number=ticket.number)


async def _deliver_ticket(message: Message, ticket: TicketMessage, lang: str) -> None:
    """Telegram half of sending a ticket — no database connection held."""
    # PIL work happens in the process pool — a burst of registrations must not
    # serialize on QR rendering in the event loop. Plain code only, no drawn
    # label: the caption already shows "№{number}" as real text, and a
    # PIL-rendered "№" glyph was missing from the fallback font, rendering as
    # a broken tofu box on some deployments.
    png = await qr_png_bytes_async(ticket.code)
    photo = BufferedInputFile(png, filename=f"navbat-{ticket.number}.png")
    await message.answer_photo(
        photo=photo, caption=ticket.caption, reply_markup=main_menu(lang)
    )


async def _status_text(session: AsyncSession, ticket: Ticket, lang: str) -> str:
    event = await session.get(SaleEvent, ticket.event_id)
    # branch tickets see only their own branch's queue
    active = await queue_service.active_tickets(session, event.id, ticket.branch_id)
    waiting_total = await queue_service.waiting_count(session, event.id, ticket.branch_id)
    desk_numbers = await queue_service.desk_numbers_for(session, active)
    if active:
        serving = ", ".join(
            f"№{a.number} ({t(lang, 'desk_short', desk=desk_numbers.get(a.desk_id, '?'))})"
            for a in active[:3]
        )
        now_line = t(lang, "now_serving", list=serving)
    else:
        now_line = t(lang, "nobody_called")

    if ticket.status == TicketStatus.CHECKED_IN:
        if event.queue_started():
            position = await queue_service.position_of(session, ticket)
            mine = t(lang, "your_pos_queue", number=ticket.number, ahead=position - 1)
        else:
            # the sale has not started — the final order is not announced yet
            mine = t(
                lang,
                "your_pos_prequeue",
                number=ticket.number,
                time=queue_service.fmt_local(event.sale_starts_at),
            )
    elif ticket.status == TicketStatus.CALLED:
        mine = t(
            lang, "your_called", number=ticket.number, desk=desk_numbers.get(ticket.desk_id, "?")
        )
    elif ticket.status == TicketStatus.REGISTERED:
        mine = t(
            lang,
            "your_registered",
            number=ticket.number,
            deadline=queue_service.fmt_local(event.checkin_until),
        )
    else:
        mine = t(
            lang, "your_status", number=ticket.number, status=status_label(lang, ticket.status)
        )
    return t(lang, "status_summary", now_line=now_line, waiting=waiting_total, mine=mine)


def _event_line(lang: str, event: SaleEvent) -> str:
    """One "upcoming sale" line; announced events lead with when the
    registration opens instead of the scanning window."""
    if event.registration_pending():
        return t(
            lang,
            "prestart_event_line",
            name=event.name,
            opens=queue_service.fmt_local(event.registration_starts_at),
            sale=queue_service.fmt_local(event.sale_starts_at),
        )
    return t(
        lang,
        "info_event_line",
        name=event.name,
        starts=queue_service.fmt_local(event.starts_at),
        deadline=queue_service.fmt_local(event.checkin_until),
    )


def _location_lines(lang: str, company: Company, branches: list[Branch]) -> list[str]:
    """Company locations, or branch addresses as fallback."""
    lines = [
        "• " + ", ".join(part for part in (loc.name, loc.address) if part)
        + (f" ({t(lang, 'info_map_link')}: {loc.map_url})" if loc.map_url else "")
        for loc in company.locations
    ]
    if not lines:
        lines = [
            "• " + ", ".join(part for part in (b.name, b.address) if part)
            for b in branches
            if b.address
        ]
    return lines


def _phone_lines(company: Company) -> list[str]:
    return [
        f"• {pretty_phone(p.phone)}" + (f" — {p.label}" if p.label else "")
        for p in company.phones
    ]


def build_info_text(
    lang: str,
    company: Company,
    events: list[SaleEvent],
    branches: list[Branch],
) -> str:
    """Company card for the ℹ️ button: name, upcoming sale dates, locations
    (company locations, or branch addresses as fallback) and phones."""
    blocks: list[str] = [f"🏢 {company.name}"]
    if events:
        lines = [_event_line(lang, e) for e in events]
        blocks.append(t(lang, "info_events_header") + ":\n" + "\n".join(lines))
    location_lines = _location_lines(lang, company, branches)
    if location_lines:
        blocks.append(t(lang, "info_locations_header") + ":\n" + "\n".join(location_lines))
    phone_lines = _phone_lines(company)
    if phone_lines:
        blocks.append(t(lang, "info_phones_header") + ":\n" + "\n".join(phone_lines))
    if len(blocks) == 1:
        blocks.append(t(lang, "info_no_details"))
    return "\n\n".join(blocks)


def build_prestart_text(
    lang: str,
    company: Company,
    events: list[SaleEvent],
    branches: list[Branch],
) -> str:
    """What the bot answers before registration opens: when registration
    opens and when the sale starts (no event name), how people will know
    registration has opened, locations, how the queue forms, and phones.

    NOTE: with more than one pending event this collapses their opens/sale
    lines together with no name to tell them apart — acceptable for the
    current single-event case; revisit if a company ever runs two
    simultaneously-announced events.
    """
    blocks: list[str] = []
    if events:
        blocks.append(
            "\n".join(
                t(
                    lang,
                    "prestart_no_name_line",
                    opens_date=e.registration_starts_at.astimezone(
                        queue_service.TASHKENT
                    ).strftime("%d.%m.%Y"),
                    sale_time=e.sale_starts_at.astimezone(queue_service.TASHKENT).strftime(
                        "%H:%M"
                    ),
                    sale_date=e.sale_starts_at.astimezone(queue_service.TASHKENT).strftime(
                        "%d.%m.%Y"
                    ),
                )
                for e in events
            )
        )
    blocks.append(t(lang, "prestart_channel_note"))
    # HTML parse mode is on for this message (the labels above are <b> bold),
    # so anything below built from staff-entered data must be escaped —
    # build_info_text's plain-text version of these same lines is untouched.
    location_lines = [html.escape(line) for line in _location_lines(lang, company, branches)]
    if location_lines:
        blocks.append(t(lang, "info_locations_header") + ":\n" + "\n".join(location_lines))
    blocks.append(t(lang, "prestart_how"))
    phone_lines = [html.escape(line) for line in _phone_lines(company)]
    if phone_lines:
        blocks.append(t(lang, "info_phones_header") + ":\n" + "\n".join(phone_lines))
    return "\n\n".join(blocks)


async def _prestart_info_text(
    session: AsyncSession, company_id: int, events: list[SaleEvent], lang: str
) -> str | None:
    """Load the company card data and render the pre-registration answer."""
    company = await session.scalar(
        select(Company)
        .where(Company.id == company_id)
        .options(selectinload(Company.phones), selectinload(Company.locations))
    )
    if company is None:
        return None
    branches = (
        await session.scalars(
            select(Branch).where(Branch.company_id == company_id).order_by(Branch.id)
        )
    ).all()
    return build_prestart_text(lang, company, events, list(branches))


# ----------------------------------------------------------------- handlers ---

async def cmd_start(message: Message, state: FSMContext, company_id: int) -> None:
    await state.clear()
    async with SessionFactory() as session:
        lang = await _stored_lang(session, company_id, message.chat.id)
    if lang is None:
        await state.set_state(Registration.choosing_language)
        await message.answer(LANGUAGE_PROMPT, reply_markup=language_keyboard())
        return
    await _start_flow(message, state, company_id, norm_lang(lang))


async def choose_language_start(
    callback: CallbackQuery, state: FSMContext, company_id: int
) -> None:
    """Language picked during /start — save it and continue registration."""
    lang = callback.data.split(":", 1)[1]
    if lang not in LANGS:
        await callback.answer()
        return
    async with SessionFactory() as session:
        await _save_lang(session, company_id, callback.message.chat.id, lang)
    await callback.answer()
    await state.clear()
    await callback.message.answer(t(lang, "language_saved"))
    await _start_flow(callback.message, state, company_id, lang)


async def change_language(callback: CallbackQuery, company_id: int) -> None:
    """Language switched from the menu (outside the registration flow)."""
    lang = callback.data.split(":", 1)[1]
    if lang not in LANGS:
        await callback.answer()
        return
    async with SessionFactory() as session:
        await _save_lang(session, company_id, callback.message.chat.id, lang)
        menu = await _menu_for(session, company_id, callback.message.chat.id, lang)
    await callback.answer()
    await callback.message.answer(t(lang, "language_saved"), reply_markup=menu)


async def _start_flow(
    message: Message, state: FSMContext, company_id: int, lang: str
) -> None:
    """Everything /start needs is read first; the answers are sent afterwards,
    with the database connection already back in the pool."""
    ticket_messages: list[TicketMessage] = []
    prestart_text: str | None = None
    menu: ReplyKeyboardMarkup | None = None
    async with SessionFactory() as session:
        events = await _open_events(session, company_id)
        tickets = await _my_tickets(session, company_id, message.chat.id)
        ticket_event_ids = {ticket.event_id for ticket in tickets}
        open_without_ticket = [e for e in events if e.id not in ticket_event_ids]
        if tickets and not open_without_ticket:
            ticket_messages = [
                await _ticket_message(session, ticket, lang) for ticket in tickets
            ]
        elif not open_without_ticket:
            # nothing open to register for — announced events answer with the
            # "sale has not started" card (opening time, queue rules,
            # locations, call-center numbers) instead of a bare refusal
            pending = await _pending_events(session, company_id)
            menu = main_menu(lang, registered=bool(tickets))
            if pending:
                prestart_text = await _prestart_info_text(
                    session, company_id, pending, lang
                )

    if tickets and not open_without_ticket:
        await message.answer(t(lang, "already_have_tickets"))
        for ticket_message in ticket_messages:
            await _deliver_ticket(message, ticket_message, lang)
        return
    if not open_without_ticket:
        if prestart_text is not None:
            await message.answer(prestart_text, reply_markup=menu, parse_mode="HTML")
            return
        await message.answer(t(lang, "no_open_events"), reply_markup=menu)
        return
    if len(open_without_ticket) == 1:
        event = open_without_ticket[0]
        await message.answer(
            t(lang, "welcome_single_event", event=event.name),
            reply_markup=ReplyKeyboardRemove(),
        )
        await _ask_branch_or_name(message, state, event, lang)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{e.name} — {queue_service.fmt_local(e.starts_at)}",
                    callback_data=f"ev:{e.id}",
                )
            ]
            for e in open_without_ticket
        ]
    )
    await state.set_state(Registration.choosing_event)
    await state.update_data(lang=lang)
    await message.answer(t(lang, "choose_event"), reply_markup=keyboard)


async def _ask_branch_or_name(
    message: Message, state: FSMContext, event: SaleEvent, lang: str
) -> None:
    """After the event is chosen: pick a branch (when the event runs in
    several), then move on to the one-line F.I.Sh. step. The queue is
    branch-scoped, so the client queues at the branch they will visit."""
    branches = list(event.branches)
    if len(branches) > 1:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=(f"{b.name} — {b.address}" if b.address else b.name)[:60],
                        callback_data=f"br:{b.id}",
                    )
                ]
                for b in branches
            ]
        )
        await state.set_state(Registration.choosing_branch)
        await state.update_data(event_id=event.id, lang=lang)
        await message.answer(t(lang, "choose_branch"), reply_markup=keyboard)
        return
    branch = branches[0] if branches else None
    await state.set_state(Registration.full_name)
    await state.update_data(event_id=event.id, branch_id=branch.id if branch else None, lang=lang)
    prefix = t(lang, "branch_line", branch=branch.name) + "\n\n" if branch else ""
    await message.answer(prefix + t(lang, "ask_fio"), reply_markup=ReplyKeyboardRemove())


async def _data_lang(state: FSMContext) -> str:
    return norm_lang((await state.get_data()).get("lang"))


def _callback_id(callback: CallbackQuery) -> int | None:
    """Numeric id from ``prefix:id`` callback data. A client is free to send
    any payload it likes, so a non-numeric one must be ignored rather than
    raise out of the handler."""
    try:
        return int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        return None


async def choose_event(callback: CallbackQuery, state: FSMContext, company_id: int) -> None:
    event_id = _callback_id(callback)
    lang = await _data_lang(state)
    if event_id is None:
        await callback.answer()
        return
    async with SessionFactory() as session:
        event = await session.get(SaleEvent, event_id)
        allowed = (
            event is not None
            and event.company_id == company_id
            and event.registration_open()
        )
        key = (
            "event_not_open_alert"
            if event is not None
            and event.company_id == company_id
            and event.registration_pending()
            else "event_closed_alert"
        )
    if not allowed:
        await callback.answer(t(lang, key), show_alert=True)
        return
    await callback.answer()
    await _ask_branch_or_name(callback.message, state, event, lang)


async def choose_branch(callback: CallbackQuery, state: FSMContext, company_id: int) -> None:
    branch_id = _callback_id(callback)
    data = await state.get_data()
    lang = norm_lang(data.get("lang"))
    if branch_id is None:
        await callback.answer()
        return
    async with SessionFactory() as session:
        event = await session.get(SaleEvent, data.get("event_id", 0))
        allowed = (
            event is not None
            and event.company_id == company_id
            and event.registration_open()
            and branch_id in event.branch_ids()
        )
        key = (
            "event_not_open_alert"
            if event is not None
            and event.company_id == company_id
            and event.registration_pending()
            else "branch_closed_alert"
        )
        branch_name = (
            next(b.name for b in event.branches if b.id == branch_id) if allowed else ""
        )
    if not allowed:
        await callback.answer(t(lang, key), show_alert=True)
        return
    await callback.answer()
    await state.set_state(Registration.full_name)
    await state.update_data(branch_id=branch_id)
    await callback.message.answer(
        t(lang, "branch_line", branch=branch_name) + "\n\n" + t(lang, "ask_fio"),
        reply_markup=ReplyKeyboardRemove(),
    )


async def reg_full_name(message: Message, state: FSMContext) -> None:
    lang = await _data_lang(state)
    parsed = split_full_name(message.text or "")
    if parsed is None:
        await message.answer(t(lang, "fio_invalid"))
        return
    first_name, last_name = parsed
    await state.update_data(first_name=first_name, last_name=last_name)
    await state.set_state(Registration.phone)
    await message.answer(t(lang, "ask_phone"), reply_markup=phone_keyboard(lang))


async def reg_phone_contact(
    message: Message, state: FSMContext, company_id: int, bot_db_id: int
) -> None:
    lang = await _data_lang(state)
    contact = message.contact
    # only the sender's own contact counts — no forwarding someone else's
    if contact.user_id is None or contact.user_id != message.from_user.id:
        await message.answer(t(lang, "phone_not_yours"), reply_markup=phone_keyboard(lang))
        return
    await _finish_registration(message, state, contact.phone_number, company_id, bot_db_id, lang)


async def reg_phone_text(message: Message, state: FSMContext) -> None:
    """Typed phone numbers are rejected — the contact button is the only way."""
    lang = await _data_lang(state)
    await message.answer(t(lang, "phone_only_button"), reply_markup=phone_keyboard(lang))


async def cmd_ticket(message: Message, company_id: int) -> None:
    async with SessionFactory() as session:
        lang = await _menu_lang(session, company_id, message.chat.id)
        tickets = await _my_tickets(session, company_id, message.chat.id)
        ticket_messages = [
            await _ticket_message(session, ticket, lang) for ticket in tickets
        ]
    if not ticket_messages:
        await message.answer(
            t(lang, "not_registered_yet"), reply_markup=main_menu(lang, registered=False)
        )
        return
    for ticket_message in ticket_messages:
        await _deliver_ticket(message, ticket_message, lang)


async def cmd_status(message: Message, company_id: int) -> None:
    async with SessionFactory() as session:
        lang = await _menu_lang(session, company_id, message.chat.id)
        tickets = await _my_tickets(session, company_id, message.chat.id)
        summaries = [await _status_text(session, ticket, lang) for ticket in tickets]
    if not summaries:
        await message.answer(
            t(lang, "not_registered_yet"), reply_markup=main_menu(lang, registered=False)
        )
        return
    for summary in summaries:
        await message.answer(summary, reply_markup=main_menu(lang))


async def cmd_info(message: Message, company_id: int) -> None:
    """Company card — always one tap away via the ℹ️ menu button or /info."""
    async with SessionFactory() as session:
        lang = await _menu_lang(session, company_id, message.chat.id)
        company = await session.scalar(
            select(Company)
            .where(Company.id == company_id)
            .options(selectinload(Company.phones), selectinload(Company.locations))
        )
        if company is None:
            return
        # announced events belong on the card too — before registration opens
        # is exactly when clients ask "when?"
        events = await _live_events(session, company_id)
        branches = (
            await session.scalars(
                select(Branch).where(Branch.company_id == company_id).order_by(Branch.id)
            )
        ).all()
        text = build_info_text(lang, company, events, list(branches))
        menu = await _menu_for(session, company_id, message.chat.id, lang)
        logo_path = (
            get_settings().upload_dir / company.logo_path if company.logo_path else None
        )
    if (
        logo_path is not None
        and logo_path.suffix.lower() in PHOTO_LOGO_SUFFIXES
        and logo_path.is_file()
    ):
        with suppress(Exception):
            if len(text) <= 1024:  # Telegram photo caption limit
                await message.answer_photo(
                    FSInputFile(logo_path), caption=text, reply_markup=menu
                )
            else:
                await message.answer_photo(FSInputFile(logo_path))
                await message.answer(text, reply_markup=menu)
            return
    await message.answer(text, reply_markup=menu)


async def cmd_language(message: Message) -> None:
    await message.answer(LANGUAGE_PROMPT, reply_markup=language_keyboard())


async def cmd_help(message: Message, company_id: int) -> None:
    async with SessionFactory() as session:
        lang = await _menu_lang(session, company_id, message.chat.id)
    await message.answer(t(lang, "help_text"))


async def fallback(message: Message, state: FSMContext, company_id: int) -> None:
    if await state.get_state() is not None:
        return
    async with SessionFactory() as session:
        lang = await _menu_lang(session, company_id, message.chat.id)
        menu = await _menu_for(session, company_id, message.chat.id, lang)
    await message.answer(t(lang, "start_over"), reply_markup=menu)


async def _dead_letter_registration(
    *,
    company_id: int,
    bot_db_id: int,
    chat_id: int,
    event_id: int | None,
    branch_id: int | None,
    first_name: str,
    last_name: str,
    phone: str,
    error: str,
) -> None:
    """Best-effort durable record of a registration that failed after
    retries, so it can be replayed instead of silently lost. Redis-only (no
    schema migration needed); if Redis is also unavailable the caller's own
    log.exception is the last line of defence."""
    redis = get_redis()
    if redis is None:
        return
    payload = json.dumps(
        {
            "company_id": company_id,
            "bot_id": bot_db_id,
            "chat_id": chat_id,
            "event_id": event_id,
            "branch_id": branch_id,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "error": error,
            "failed_at": now_utc().isoformat(),
        }
    )
    with suppress(Exception):
        await redis.lpush(DEAD_LETTER_KEY, payload)


async def _finish_registration(
    message: Message,
    state: FSMContext,
    raw_phone: str,
    company_id: int,
    bot_db_id: int,
    lang: str,
) -> None:
    # only +998 Uzbek numbers pass normalize_phone — anything else is refused
    phone = normalize_phone(raw_phone)
    if phone is None:
        await message.answer(t(lang, "phone_invalid"), reply_markup=phone_keyboard(lang))
        return
    data = await state.get_data()

    outcome: str | None = None
    ticket_message: TicketMessage | None = None
    menu: ReplyKeyboardMarkup | None = None
    prestart_text: str | None = None
    rejection: str | None = None

    # Transient failures (DB/connection hiccups etc.) get a couple of retries
    # on a FRESH session each time before giving up — DomainError is a real
    # rejection and is handled inline below, never retried. Retrying the
    # whole block is safe: the phone-existing-ticket check makes it
    # idempotent even if a prior attempt actually committed before failing.
    # Only the DATABASE work is retried: a Telegram send that fails must never
    # replay the registration, which used to answer a client whose ticket had
    # just been created with "this phone already has one".
    for attempt in range(1, _REGISTRATION_RETRY_ATTEMPTS + 1):
        try:
            async with SessionFactory() as session:
                event = await session.get(SaleEvent, data["event_id"])
                if event is None or not event.registration_open():
                    await state.clear()
                    menu = await _menu_for(session, company_id, message.chat.id, lang)
                    # the owner can move the opening time while a client is mid-flow:
                    # answer with the full "sale has not started" card, not "closed"
                    if event is not None and event.registration_pending():
                        prestart_text = await _prestart_info_text(
                            session, company_id, [event], lang
                        )
                    outcome = "closed"
                    break
                # one phone = one ticket per event: a duplicate gets the existing one
                existing = await ticket_service.get_ticket_by_phone(session, event.id, phone)
                if existing is not None:
                    await state.clear()
                    if existing.telegram_chat_id is None or existing.bot_id is None:
                        if existing.telegram_chat_id is None:
                            existing.telegram_chat_id = message.chat.id
                        if existing.bot_id is None:
                            existing.bot_id = bot_db_id
                        await session.commit()
                    ticket_message = await _ticket_message(session, existing, lang)
                    outcome = "taken"
                    break
                try:
                    ticket = await ticket_service.create_ticket(
                        session,
                        event,
                        first_name=data["first_name"],
                        last_name=data["last_name"],
                        phone=phone,
                        telegram_chat_id=message.chat.id,
                        branch_id=data.get("branch_id"),
                        bot_id=bot_db_id,
                    )
                except DomainError as exc:
                    await state.clear()
                    menu = await _menu_for(session, company_id, message.chat.id, lang)
                    rejection = exc.message
                    outcome = "rejected"
                    break
                await state.clear()
                queue_service.schedule_event_broadcast(event.id)
                # a registration after the scanning window still gets a QR, but the
                # client is told up front they will join the end-of-day queue
                late_born = ticket.registered_at >= event.checkin_until
                outcome = "registered_late" if late_born else "registered"
                ticket_message = await _ticket_message(session, ticket, lang)
                log.info(
                    "New ticket #%s (%s) for event %s via bot", ticket.number, phone, event.id
                )
                break
        except Exception as exc:
            if attempt == _REGISTRATION_RETRY_ATTEMPTS:
                log.exception(
                    "Registration failed after %s attempts (phone %s, event %s)",
                    attempt,
                    phone,
                    data.get("event_id"),
                )
                await _dead_letter_registration(
                    company_id=company_id,
                    bot_db_id=bot_db_id,
                    chat_id=message.chat.id,
                    event_id=data.get("event_id"),
                    branch_id=data.get("branch_id"),
                    first_name=data.get("first_name", ""),
                    last_name=data.get("last_name", ""),
                    phone=phone,
                    error=repr(exc),
                )
                await state.clear()
                with suppress(Exception):
                    await message.answer(
                        t(lang, "registration_retry_later"),
                        reply_markup=main_menu(lang, registered=False),
                    )
                return
            log.warning(
                "Registration attempt %s/%s failed transiently (phone %s): %s",
                attempt,
                _REGISTRATION_RETRY_ATTEMPTS,
                phone,
                exc,
            )
            await asyncio.sleep(_REGISTRATION_RETRY_BASE_DELAY * attempt)

    # Every answer goes out here, with the pooled connection already returned:
    # a QR upload paced by the per-bot rate limiter can sleep for seconds, and
    # holding a connection for that long is what starves the pool in a burst.
    if outcome == "closed":
        if prestart_text is not None:
            await message.answer(prestart_text, reply_markup=menu, parse_mode="HTML")
        else:
            await message.answer(t(lang, "registration_closed"), reply_markup=menu)
    elif outcome == "taken":
        await message.answer(t(lang, "phone_taken"), reply_markup=main_menu(lang))
        await _deliver_ticket(message, ticket_message, lang)
    elif outcome == "rejected":
        await message.answer(rejection, reply_markup=menu)
    elif outcome in ("registered", "registered_late"):
        ok_key = "registered_ok_late" if outcome == "registered_late" else "registered_ok"
        await message.answer(t(lang, ok_key), reply_markup=main_menu(lang))
        await _deliver_ticket(message, ticket_message, lang)


async def menu_ticket(message: Message, company_id: int) -> None:
    await cmd_ticket(message, company_id)


async def menu_status(message: Message, company_id: int) -> None:
    await cmd_status(message, company_id)


async def menu_info(message: Message, company_id: int) -> None:
    await cmd_info(message, company_id)


def build_router() -> Router:
    """Fresh Router wired to the shared handlers (a Router instance cannot be
    attached to more than one Dispatcher)."""
    router = Router()
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_ticket, Command("navbat", "ticket"))
    router.message.register(cmd_status, Command("holat", "status"))
    router.message.register(cmd_info, Command("info", "malumot"))
    router.message.register(cmd_help, Command("help"))
    router.callback_query.register(
        choose_language_start, Registration.choosing_language, F.data.startswith("lang:")
    )
    router.callback_query.register(change_language, F.data.startswith("lang:"))
    router.callback_query.register(
        choose_event, Registration.choosing_event, F.data.startswith("ev:")
    )
    router.callback_query.register(
        choose_branch, Registration.choosing_branch, F.data.startswith("br:")
    )
    router.message.register(reg_full_name, Registration.full_name, F.text)
    router.message.register(reg_phone_contact, Registration.phone, F.contact)
    router.message.register(reg_phone_text, Registration.phone, F.text)
    router.message.register(menu_ticket, F.text.in_(BTN_TICKET_ALL))
    router.message.register(menu_status, F.text.in_(BTN_STATUS_ALL))
    router.message.register(menu_info, F.text.in_(BTN_INFO_ALL))
    router.message.register(cmd_language, F.text.in_(BTN_LANG_ALL))
    router.message.register(fallback, F.text)
    return router
