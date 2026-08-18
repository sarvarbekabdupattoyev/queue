"""Per-company Telegram bot conversation.

/start → (choose event if several are open) → first name → last name → phone
(contact button or typed) → ticket with a random 4-digit number + QR photo.
"""

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import normalize_phone, pretty_phone
from app.db.base import now_utc
from app.db.session import SessionFactory
from app.models import SaleEvent, Ticket, TicketStatus
from app.services import queue_service, ticket_service
from app.services.errors import DomainError
from app.services.qr_service import qr_png_bytes

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЎўҚқҒғҲҳXxOoʻʼ'’‘\- ]{2,30}$")

BTN_MY_TICKET = "🎫 Mening navbatim"
BTN_STATUS = "📊 Navbat holati"

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_MY_TICKET), KeyboardButton(text=BTN_STATUS)]],
    resize_keyboard=True,
    is_persistent=True,
)

STATUS_UZ = {
    TicketStatus.REGISTERED: "Ro'yxatdan o'tgan (hali kelmagan)",
    TicketStatus.CHECKED_IN: "Keldi — navbat kutmoqda",
    TicketStatus.CALLED: "Chaqirildi",
    TicketStatus.SERVING: "Xizmat ko'rsatilmoqda",
    TicketStatus.DONE: "Yakunlandi",
    TicketStatus.SKIPPED: "O'tkazib yuborilgan (kelmadi)",
    TicketStatus.CANCELLED: "Bekor qilingan",
}


class Registration(StatesGroup):
    choosing_event = State()
    first_name = State()
    last_name = State()
    phone = State()


def _cap(value: str) -> str:
    value = value.strip()
    return value[:1].upper() + value[1:] if value else value


async def _open_events(session: AsyncSession, company_id: int) -> list[SaleEvent]:
    events = (
        await session.scalars(
            select(SaleEvent)
            .where(SaleEvent.company_id == company_id, SaleEvent.is_active.is_(True))
            .order_by(SaleEvent.starts_at)
        )
    ).all()
    now = now_utc()
    return [e for e in events if e.registration_open(now)]


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


async def _send_ticket(message: Message, session: AsyncSession, ticket: Ticket, intro: str = "") -> None:
    event = await session.get(SaleEvent, ticket.event_id)
    caption = (
        f"{intro}🎫 Navbat raqamingiz: №{ticket.number}\n"
        f"🗓 {event.name} — {queue_service.fmt_local(event.starts_at)}\n"
        f"👤 {ticket.full_name}\n"
        f"📞 {pretty_phone(ticket.phone)}\n\n"
        f"Ofisga kelganda shu QR-kodni qabulxonada ko'rsating — kelganingiz qayd etiladi. "
        f"Skanerlash {queue_service.fmt_local(event.checkin_until)} gacha. Navbat tartibi "
        f"ro'yxatdan o'tgan vaqtingiz bo'yicha belgilanadi.\n\n"
        f"Holat: {STATUS_UZ[ticket.status]}"
    )
    photo = BufferedInputFile(qr_png_bytes(ticket.code), filename=f"navbat-{ticket.number}.png")
    await message.answer_photo(photo=photo, caption=caption, reply_markup=MAIN_MENU)


async def _status_text(session: AsyncSession, ticket: Ticket) -> str:
    event = await session.get(SaleEvent, ticket.event_id)
    active = await queue_service.active_tickets(session, event.id)
    waiting = await queue_service.waiting_tickets(session, event.id)
    desk_numbers = await queue_service.desk_numbers_for(session, active)
    if active:
        serving = ", ".join(
            f"№{t.number} ({desk_numbers.get(t.desk_id, '?')}-stol)" for t in active[:3]
        )
        now_line = f"Hozir {serving} qabul qilinmoqda."
    else:
        now_line = "Hozircha hech kim chaqirilmagan."

    if ticket.status == TicketStatus.CHECKED_IN:
        position = await queue_service.position_of(session, ticket)
        if event.queue_started():
            mine = f"Sizning raqamingiz: №{ticket.number}. Sizdan oldin {position - 1} kishi bor."
        else:
            mine = (
                f"Sizning raqamingiz: №{ticket.number}. Navbat "
                f"{queue_service.fmt_local(event.checkin_until)} da boshlanadi — hozircha "
                f"{position}-o'rindasiz."
            )
    elif ticket.status == TicketStatus.CALLED:
        desk = desk_numbers.get(ticket.desk_id, "?")
        mine = f"Sizning raqamingiz: №{ticket.number} — chaqirilgansiz! {desk}-stolga yaqinlashing."
    elif ticket.status == TicketStatus.REGISTERED:
        mine = (
            f"Sizning raqamingiz: №{ticket.number}. Ofisga kelganda QR-kodni qabulxonada "
            f"ko'rsating ({queue_service.fmt_local(event.checkin_until)} gacha)."
        )
    else:
        mine = f"Sizning raqamingiz: №{ticket.number}. Holat: {STATUS_UZ[ticket.status]}."
    return f"📊 {now_line} Kutayotganlar: {len(waiting)} kishi.\n\n{mine}"


def build_router(company_id: int) -> Router:
    router = Router(name=f"company-{company_id}")

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        async with SessionFactory() as session:
            events = await _open_events(session, company_id)
            tickets = await _my_tickets(session, company_id, message.chat.id)
            ticket_event_ids = {t.event_id for t in tickets}
            open_without_ticket = [e for e in events if e.id not in ticket_event_ids]

            if tickets and not open_without_ticket:
                await message.answer("Siz allaqachon ro'yxatdan o'tgansiz. Mana navbatingiz:")
                for ticket in tickets:
                    await _send_ticket(message, session, ticket)
                return
            if not open_without_ticket:
                await message.answer(
                    "Hozircha ochiq tadbirlar yo'q. Tadbir e'lon qilinganda qayta urinib ko'ring.",
                    reply_markup=MAIN_MENU,
                )
                return
            if len(open_without_ticket) == 1:
                event = open_without_ticket[0]
                await state.set_state(Registration.first_name)
                await state.update_data(event_id=event.id)
                await message.answer(
                    f"Assalomu alaykum! «{event.name}» uchun onlayn navbat botiga xush kelibsiz.\n\n"
                    "Ro'yxatdan o'tish uchun 3 ta ma'lumot kerak: ism, familiya va telefon raqam. "
                    "Bitta telefonga bitta navbat beriladi.\n\n1/3 — Ismingizni yozing:",
                    reply_markup=ReplyKeyboardRemove(),
                )
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
            await message.answer(
                "Assalomu alaykum! Qaysi tadbir uchun navbat olasiz?", reply_markup=keyboard
            )

    @router.callback_query(Registration.choosing_event, F.data.startswith("ev:"))
    async def choose_event(callback: CallbackQuery, state: FSMContext) -> None:
        event_id = int(callback.data.split(":", 1)[1])
        async with SessionFactory() as session:
            event = await session.get(SaleEvent, event_id)
            if event is None or event.company_id != company_id or not event.registration_open():
                await callback.answer("Bu tadbir uchun ro'yxat yopilgan", show_alert=True)
                return
        await callback.answer()
        await state.set_state(Registration.first_name)
        await state.update_data(event_id=event_id)
        await callback.message.answer(
            "1/3 — Ismingizni yozing:", reply_markup=ReplyKeyboardRemove()
        )

    @router.message(Command("navbat", "ticket"))
    async def cmd_ticket(message: Message) -> None:
        async with SessionFactory() as session:
            tickets = await _my_tickets(session, company_id, message.chat.id)
            if not tickets:
                await message.answer("Siz hali ro'yxatdan o'tmagansiz. /start ni bosing.")
                return
            for ticket in tickets:
                await _send_ticket(message, session, ticket)

    @router.message(Command("holat", "status"))
    async def cmd_status(message: Message) -> None:
        await _answer_status(message)

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "/start — ro'yxatdan o'tish\n/navbat — mening navbatim (QR-kod)\n/holat — navbat holati"
        )

    @router.message(Registration.first_name, F.text)
    async def reg_first_name(message: Message, state: FSMContext) -> None:
        text = message.text.strip()
        if not NAME_RE.fullmatch(text):
            await message.answer("Iltimos, faqat harflardan iborat ism yozing (2–30 belgi).")
            return
        await state.update_data(first_name=_cap(text))
        await state.set_state(Registration.last_name)
        await message.answer("2/3 — Familiyangizni yozing:")

    @router.message(Registration.last_name, F.text)
    async def reg_last_name(message: Message, state: FSMContext) -> None:
        text = message.text.strip()
        if not NAME_RE.fullmatch(text):
            await message.answer("Iltimos, faqat harflardan iborat familiya yozing (2–30 belgi).")
            return
        await state.update_data(last_name=_cap(text))
        await state.set_state(Registration.phone)
        await message.answer(
            "3/3 — Telefon raqamingizni yuboring. Pastdagi «📱 Raqamni yuborish» tugmasini "
            "bosing yoki raqamni yozing (masalan, +998 90 123 45 67).",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )

    @router.message(Registration.phone, F.contact)
    async def reg_phone_contact(message: Message, state: FSMContext) -> None:
        await _finish_registration(message, state, message.contact.phone_number)

    @router.message(Registration.phone, F.text)
    async def reg_phone_text(message: Message, state: FSMContext) -> None:
        await _finish_registration(message, state, message.text)

    @router.message(F.text == BTN_MY_TICKET)
    async def menu_ticket(message: Message) -> None:
        await cmd_ticket(message)

    @router.message(F.text == BTN_STATUS)
    async def menu_status(message: Message) -> None:
        await _answer_status(message)

    @router.message(F.text)
    async def fallback(message: Message, state: FSMContext) -> None:
        if await state.get_state() is None:
            await message.answer(
                "Ro'yxatdan o'tish uchun /start ni bosing.", reply_markup=MAIN_MENU
            )

    async def _answer_status(message: Message) -> None:
        async with SessionFactory() as session:
            tickets = await _my_tickets(session, company_id, message.chat.id)
            if not tickets:
                await message.answer("Siz hali ro'yxatdan o'tmagansiz. /start ni bosing.")
                return
            for ticket in tickets:
                await message.answer(await _status_text(session, ticket), reply_markup=MAIN_MENU)

    async def _finish_registration(message: Message, state: FSMContext, raw_phone: str) -> None:
        phone = normalize_phone(raw_phone)
        if phone is None:
            await message.answer("Raqam noto'g'ri. O'zbekiston raqamini kiriting: +998 XX XXX XX XX")
            return
        data = await state.get_data()
        async with SessionFactory() as session:
            event = await session.get(SaleEvent, data["event_id"])
            if event is None or not event.registration_open():
                await state.clear()
                await message.answer(
                    "Afsuski, bu tadbir uchun ro'yxat yopildi.", reply_markup=MAIN_MENU
                )
                return
            existing = await ticket_service.get_ticket_by_phone(session, event.id, phone)
            if existing is not None:
                await state.clear()
                if existing.telegram_chat_id is None:
                    existing.telegram_chat_id = message.chat.id
                    await session.commit()
                await message.answer(
                    "Bu telefon raqamiga navbat allaqachon berilgan. Mana u:",
                    reply_markup=MAIN_MENU,
                )
                await _send_ticket(message, session, existing)
                return
            try:
                ticket = await ticket_service.create_ticket(
                    session,
                    event,
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    phone=phone,
                    telegram_chat_id=message.chat.id,
                )
            except DomainError as exc:
                await state.clear()
                await message.answer(exc.message, reply_markup=MAIN_MENU)
                return
            await state.clear()
            await queue_service.broadcast_event(session, event)
            await message.answer("✅ Ro'yxatdan o'tdingiz!", reply_markup=MAIN_MENU)
            await _send_ticket(message, session, ticket)
            log.info(
                "New ticket #%s (%s) for event %s via bot", ticket.number, phone, event.id
            )

    return router
