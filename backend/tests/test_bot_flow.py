"""Bot conversation building blocks: the trilingual message table, one-line
F.I.Sh. parsing, per-chat language storage, and localized queue
notifications."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.base import now_utc
from app.db.session import SessionFactory
from app.models import BotUser, Company, SaleEvent, TicketStatus
from app.services import i18n, notify, queue_service, ticket_service
from app.services.i18n import _T, t
from app.services.telegram.handlers import (
    _open_events,
    _pending_events,
    _prestart_info_text,
    _save_lang,
    _stored_lang,
    build_info_text,
    split_full_name,
)
from tests.conftest import auth, create_company, event_times, register_owner

NOW = now_utc


async def _wait_for(predicate, timeout: float = 3.0) -> None:
    import asyncio

    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


def test_i18n_table_is_complete():
    for key, per_lang in _T.items():
        assert set(per_lang) == set(i18n.LANGS), f"{key} missing a language"
        for lang, text in per_lang.items():
            assert text.strip(), f"{key}/{lang} is empty"
    for status in TicketStatus:
        for lang in i18n.LANGS:
            assert i18n.status_label(lang, status)


def test_i18n_falls_back_to_uzbek():
    assert t(None, "registered_ok") == t("uz", "registered_ok")
    assert t("de", "registered_ok") == t("uz", "registered_ok")
    # formatting-heavy keys render in every language without KeyError
    for lang in i18n.LANGS:
        text = t(
            lang,
            "ticket_caption",
            intro="", number="KJZR", event="Sotuv", starts="09:00 (01.09.2026)",
            branch_line="", name="Test Testov", phone="+998 90 123 45 67",
            reg_time="08:12:31.204 (01.09.2026)",
            deadline="10:00 (01.09.2026)", status="ok",
        )
        assert "KJZR" in text
        # the registration moment (with milliseconds) is part of the ticket
        assert "08:12:31.204" in text
        assert t(lang, "ntf_called", number=1, desk=2, minutes=3)


def test_menu_hides_ticket_buttons_until_registered():
    """An unregistered chat sees only the info and language buttons."""
    from app.services.telegram.handlers import main_menu

    def texts(markup):
        return {button.text for row in markup.keyboard for button in row}

    for lang in i18n.LANGS:
        anonymous = texts(main_menu(lang, registered=False))
        registered = texts(main_menu(lang, registered=True))
        assert t(lang, "btn_ticket") not in anonymous
        assert t(lang, "btn_status") not in anonymous
        assert t(lang, "btn_info") in anonymous and t(lang, "btn_language") in anonymous
        assert t(lang, "btn_ticket") in registered and t(lang, "btn_status") in registered


def test_only_uzbek_phone_numbers_are_accepted():
    from app.core.phone import normalize_phone

    assert normalize_phone("+998 90 123 45 67") == "+998901234567"
    assert normalize_phone("901234567") == "+998901234567"
    # anything that is not an Uzbek +998 number is refused
    assert normalize_phone("+7 900 123 45 67") is None
    assert normalize_phone("+1 202 555 0100") is None
    assert normalize_phone("+99890123456") is None  # too short


def test_split_full_name_parses_one_line_fio():
    assert split_full_name("sardor rahimov akmal o'g'li") == ("Sardor", "Rahimov Akmal O'g'li")
    assert split_full_name("Dilnoza Xolmatova") == ("Dilnoza", "Xolmatova")
    assert split_full_name("Сардор Рахимов Акмал угли") == ("Сардор", "Рахимов Акмал Угли")
    assert split_full_name("Sardor") is None            # surname required
    assert split_full_name("Sardor R4himov") is None    # digits rejected
    assert split_full_name("a b") is None               # too-short words
    assert split_full_name("A B C D E F") is None       # too many words
    assert split_full_name("Sardor " + "Juda" * 20) is None  # over the column cap


async def test_language_is_stored_per_company_chat(client):
    token = (await register_owner(client))["access_token"]
    company = await create_company(client, token)

    async with SessionFactory() as db:
        assert await _stored_lang(db, company["id"], 777) is None
        await _save_lang(db, company["id"], 777, "ru")
        assert await _stored_lang(db, company["id"], 777) == "ru"
        # saving again updates the same row instead of duplicating it
        await _save_lang(db, company["id"], 777, "en")
        assert await _stored_lang(db, company["id"], 777) == "en"
        count = await db.scalar(
            select(func.count()).select_from(BotUser).where(BotUser.chat_id == 777)
        )
        assert count == 1


async def test_notifications_use_the_client_language(client, monkeypatch):
    token = (await register_owner(client))["access_token"]
    company = await create_company(client, token)
    event_resp = await client.post(
        "/api/events",
        json={"name": "Sotuv kuni", **event_times()},
        headers=auth(token),
    )
    event_id = event_resp.json()["id"]

    sent: list[tuple[int, str]] = []

    async def fake_send(company_id, chat_id, text, bot_id=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(notify, "send_telegram_text", fake_send)

    async with SessionFactory() as db:
        await _save_lang(db, company["id"], 555, "ru")
        event = await db.get(SaleEvent, event_id)
        ticket = await ticket_service.create_ticket(
            db, event, first_name="Иван", last_name="Иванов", phone="+998901112233",
            telegram_chat_id=555,
        )
        number = ticket.number

    checkin = await client.post(
        f"/api/queue/{event_id}/checkin", json={"number": number}, headers=auth(token)
    )
    assert checkin.status_code == 200, checkin.text
    await _wait_for(lambda: len(sent) == 1)
    chat_id, text = sent[0]
    assert chat_id == 555
    # before the sale starts the notification carries NO queue position
    assert text == t("ru", "ntf_checkin_prequeue", number=number,
                     time=queue_service.fmt_local(event.sale_starts_at))
    assert "мест" not in text


async def test_company_info_text_lists_everything(client):
    token = (await register_owner(client))["access_token"]
    company_data = await create_company(client, token)
    await client.post(
        "/api/company/phones",
        json={"phone": "+998712005050", "label": "Call-markaz"},
        headers=auth(token),
    )
    await client.post(
        "/api/company/locations",
        json={"name": "Bosh ofis", "address": "Toshkent, Yunusobod 4-mavze"},
        headers=auth(token),
    )
    event_resp = await client.post(
        "/api/events",
        json={
            "name": "Katta sotuv",
            **event_times(
                reg_min=24 * 60, starts_min=24 * 60, checkin_min=26 * 60, sale_min=26 * 60
            ),
        },
        headers=auth(token),
    )
    assert event_resp.status_code == 201

    async with SessionFactory() as db:
        company = await db.scalar(
            select(Company)
            .where(Company.id == company_data["id"])
            .options(selectinload(Company.phones), selectinload(Company.locations))
        )
        events = (await db.scalars(select(SaleEvent))).all()
        for lang in i18n.LANGS:
            text = build_info_text(lang, company, list(events), [])
            assert company.name in text
            assert "Katta sotuv" in text
            assert "Bosh ofis" in text
            assert "+998 71 200 50 50" in text
            assert t(lang, "info_phones_header") in text


async def test_bot_answers_with_prestart_card_before_registration_opens(client):
    """Before ``registration_starts_at`` the bot offers nothing to register
    for; /start answers with the card: the sale has not started + when
    registration opens + how the queue forms + locations + call-center
    numbers."""
    token = (await register_owner(client))["access_token"]
    company_data = await create_company(client, token)
    await client.post(
        "/api/company/phones",
        json={"phone": "+998712005050", "label": "Call-markaz"},
        headers=auth(token),
    )
    await client.post(
        "/api/company/locations",
        json={"name": "Bosh ofis", "address": "Toshkent, Yunusobod 4-mavze"},
        headers=auth(token),
    )
    event_resp = await client.post(
        "/api/events",
        json={
            "name": "Katta sotuv",
            **event_times(reg_min=90, starts_min=120, checkin_min=150, sale_min=180),
        },
        headers=auth(token),
    )
    assert event_resp.status_code == 201, event_resp.text

    async with SessionFactory() as db:
        assert await _open_events(db, company_data["id"]) == []
        pending = await _pending_events(db, company_data["id"])
        assert [e.name for e in pending] == ["Katta sotuv"]
        for lang in i18n.LANGS:
            text = await _prestart_info_text(db, company_data["id"], pending, lang)
            assert text is not None
            # deliberately no event name before the sale is announced publicly
            assert "Katta sotuv" not in text
            assert queue_service.fmt_local(pending[0].registration_starts_at) in text
            assert queue_service.fmt_local(pending[0].sale_starts_at) in text
            assert t(lang, "prestart_channel_note") in text
            assert t(lang, "prestart_how") in text
            assert "Bosh ofis" in text
            assert "+998 71 200 50 50" in text
