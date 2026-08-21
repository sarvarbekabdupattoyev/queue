"""Regressions from the code review: concurrent staff actions, the one-client-
per-desk guarantee, burst-scale queries, and the hardened edges (bounded
listings, webhook auth, broadcast retries, slow WebSocket clients)."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionFactory
from app.models import BotUser, SaleEvent, Ticket, TicketStatus
from app.services import broadcast, queue_service
from app.services.errors import ConflictError, DomainError
import app.ws.manager as manager_module
from app.services.telegram.manager import bot_manager, webhook_secret
from app.ws.manager import ws_manager
from tests.conftest import auth, create_company, register_owner, started_sale_times
from tests.test_queue_logic import (
    close_checkin_window,
    create_event,
    make_ticket,
    setup_company,
)


async def _checked_in_event(client, desks: int = 2, tickets: int = 3):
    """An event whose sale is running, with `tickets` clients checked in."""
    token, desk_ids = await setup_company(client, desks=desks)
    event = await create_event(client, token)
    made = [
        await make_ticket(event["id"], f"+99890111{n:04d}", n) for n in range(tickets)
    ]
    for ticket in made:
        response = await client.post(
            f"/api/queue/{event['id']}/checkin",
            json={"code": ticket["code"]},
            headers=auth(token),
        )
        assert response.status_code == 200, response.text
    await close_checkin_window(client, token, event["id"])
    return token, event, desk_ids, made


# ------------------------------------------------- one client per desk ---

async def test_desk_cannot_hold_two_active_tickets(client):
    """The busy check in call_next and the claim that follows are separate
    transactions, so the database is what has to refuse the second client."""
    token, event, desk_ids, made = await _checked_in_event(client)
    called = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_ids[0]},
        headers=auth(token),
    )
    assert called.status_code == 200, called.text

    async with SessionFactory() as db:
        waiting = await db.scalar(
            select(Ticket).where(
                Ticket.event_id == event["id"], Ticket.status == TicketStatus.CHECKED_IN
            )
        )
        waiting.status = TicketStatus.CALLED
        waiting.desk_id = desk_ids[0]
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


async def test_second_call_at_a_busy_desk_is_refused(client):
    token, event, desk_ids, made = await _checked_in_event(client)
    first = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_ids[0]},
        headers=auth(token),
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_ids[0]},
        headers=auth(token),
    )
    assert second.status_code == 409, second.text


# --------------------------------------------- atomic staff transitions ---

async def test_cancel_loses_to_a_concurrent_finish(client):
    """Two staff screens hold the same ticket; whoever commits second must be
    told no, not silently overwrite a finished sale."""
    token, event, desk_ids, made = await _checked_in_event(client)
    await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_ids[0]},
        headers=auth(token),
    )
    async with SessionFactory() as db:
        called = await db.scalar(
            select(Ticket).where(
                Ticket.event_id == event["id"], Ticket.status == TicketStatus.CALLED
            )
        )
        number = called.number

    # each "request" loads its own copy, exactly like two API calls would
    async with SessionFactory() as finisher, SessionFactory() as canceller:
        event_a = await finisher.get(SaleEvent, event["id"])
        event_b = await canceller.get(SaleEvent, event["id"])
        ticket_a = await queue_service.get_ticket_by_number(finisher, event["id"], number)
        ticket_b = await queue_service.get_ticket_by_number(canceller, event["id"], number)
        await queue_service.finish(finisher, event_a, ticket_a, contract_signed=True)
        with pytest.raises(DomainError):
            await queue_service.cancel(canceller, event_b, ticket_b)

    async with SessionFactory() as db:
        final = await queue_service.get_ticket_by_number(db, event["id"], number)
        assert final.status == TicketStatus.DONE
        assert final.contract_signed is True


async def test_skip_counts_are_not_lost_between_sessions(client):
    """skip_count is incremented in SQL, so a stale in-memory copy cannot
    overwrite it back to an earlier value."""
    token, event, desk_ids, made = await _checked_in_event(client, tickets=1)
    await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_ids[0]},
        headers=auth(token),
    )
    async with SessionFactory() as db:
        ticket = await db.scalar(
            select(Ticket).where(Ticket.event_id == event["id"])
        )
        number, before = ticket.number, ticket.skip_count
    response = await client.post(
        f"/api/queue/{event['id']}/skip", json={"number": number}, headers=auth(token)
    )
    assert response.status_code == 200, response.text
    async with SessionFactory() as db:
        ticket = await queue_service.get_ticket_by_number(db, event["id"], number)
        assert ticket.skip_count == before + 1
        assert ticket.desk_id is None


async def test_ahead_never_does_arithmetic_on_a_missing_position():
    # a desk may call a ticket between the check-in claim and the position read
    assert queue_service._ahead(None) == 0
    assert queue_service._ahead(1) == 0
    assert queue_service._ahead(7) == 6


# -------------------------------------------------------- burst queries ---

async def test_sale_start_notifies_everyone_across_lookup_chunks(
    client, monkeypatch
):
    """The language lookup binds one parameter per chat id, so it is chunked —
    every checked-in client must still get exactly one message."""
    sent: list[int] = []

    async def fake_send(company_id, chat_id, text, bot_id=None):
        sent.append(chat_id)

    from app.services import notify

    monkeypatch.setattr(notify, "send_telegram_text", fake_send)
    monkeypatch.setattr(queue_service, "LANG_LOOKUP_CHUNK", 2)

    token, desk_ids = await setup_company(client)
    event = await create_event(client, token)
    made = [await make_ticket(event["id"], f"+99890222{n:04d}", n) for n in range(5)]
    async with SessionFactory() as db:
        sale_event = await db.get(SaleEvent, event["id"])
        company_id = sale_event.company_id
        for index, ticket in enumerate(made):
            row = await db.get(Ticket, ticket["id"])
            row.telegram_chat_id = 9000 + index
            db.add(BotUser(company_id=company_id, chat_id=9000 + index, language="ru"))
        await db.commit()
    for ticket in made:
        await client.post(
            f"/api/queue/{event['id']}/checkin",
            json={"code": ticket["code"]},
            headers=auth(token),
        )
    await close_checkin_window(client, token, event["id"])

    sent.clear()  # check-in confirmations already went out; count only the burst
    async with SessionFactory() as db:
        row = await db.get(SaleEvent, event["id"])
        assert await queue_service.notify_sale_started(db, row) == 5
    assert sorted(sent) == [9000 + n for n in range(5)]


async def test_ticket_listing_rejects_an_unbounded_window(client):
    token, desk_ids = await setup_company(client)
    event = await create_event(client, token)
    # LIMIT -1 used to reach the database: an error on PostgreSQL, the whole
    # event (phone numbers included) on SQLite
    response = await client.get(
        f"/api/events/{event['id']}/tickets?limit=-1", headers=auth(token)
    )
    assert response.status_code == 422
    too_many = await client.get(
        f"/api/events/{event['id']}/tickets?limit=5000", headers=auth(token)
    )
    assert too_many.status_code == 422


async def test_public_state_skips_the_staff_payload(client):
    """The TV board must not build a staff entry per waiting ticket."""
    token, event, desk_ids, made = await _checked_in_event(client)
    async with SessionFactory() as db:
        row = await db.get(SaleEvent, event["id"])
        public, staff = await queue_service.build_states(db, row, include_staff=False)
    assert staff == {}
    assert public["next"] and "phone" not in public["next"][0]


# ------------------------------------------------------------ hardening ---

async def test_webhook_secret_check_survives_a_junk_header():
    """A non-ASCII header used to raise TypeError out of compare_digest —
    an unauthenticated 500."""
    assert bot_manager.verify_webhook(1, "salom-👋") is False
    assert bot_manager.verify_webhook(1, webhook_secret(1)) is False  # no such bot


async def test_broadcast_retries_after_a_failed_rebuild(client, monkeypatch):
    token, desk_ids = await setup_company(client)
    event = await create_event(client, token)
    attempts: list[int] = []

    async def flaky(event_id: int) -> None:
        attempts.append(event_id)
        if len(attempts) == 1:
            raise RuntimeError("database went away")

    monkeypatch.setattr(broadcast, "_build_and_publish", flaky)
    broadcast.schedule_event_broadcast(event["id"])
    await asyncio.sleep(0.4)
    # the pending change is retried instead of being dropped until the next
    # mutation happens to succeed
    assert len(attempts) >= 2


async def test_one_stalled_screen_does_not_block_the_others(monkeypatch):
    class Stalled:
        async def send_text(self, message: str) -> None:
            await asyncio.sleep(30)

    class Fine:
        def __init__(self) -> None:
            self.got: list[str] = []

        async def send_text(self, message: str) -> None:
            self.got.append(message)

    stalled, fine = Stalled(), Fine()
    room = "display:999"
    async with ws_manager._lock:
        ws_manager._rooms[room].update({stalled, fine})
    # keep the test quick: the production cap is seconds, not minutes
    monkeypatch.setattr(manager_module, "SEND_TIMEOUT_S", 0.05)
    try:
        await ws_manager.deliver_local(room, "state")
        assert fine.got == ["state"]  # delivered despite the stalled peer
        async with ws_manager._lock:
            # the screen that could not keep up is dropped, not left to stall
            # every future broadcast; it reconnects and re-snapshots
            assert stalled not in ws_manager._rooms.get(room, set())
    finally:
        async with ws_manager._lock:
            ws_manager._rooms.pop(room, None)
