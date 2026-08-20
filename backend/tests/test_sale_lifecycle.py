"""The three-period model: the registration gate, the sale
start/hold/end/reopen controls, the one-time sale-start notification burst,
staff walk-ins and single-use QR codes."""

import re
from datetime import timedelta

from sqlalchemy import select

from app.db.base import now_utc
from app.db.session import SessionFactory
from app.models import SaleEvent, Ticket
from app.services import notify, queue_service, ticket_service
from app.services.errors import DomainError
from tests.conftest import auth, event_times, started_sale_times
from tests.test_queue_logic import close_checkin_window, create_event, make_ticket, setup_company


async def checkin(client, token, event_id, number):
    response = await client.post(
        f"/api/queue/{event_id}/checkin", json={"number": number}, headers=auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def get_event(client, token, event_id):
    return (await client.get(f"/api/events/{event_id}", headers=auth(token))).json()


async def sale_action(client, token, event_id, action, expect=200):
    response = await client.post(
        f"/api/events/{event_id}/sale", json={"action": action}, headers=auth(token)
    )
    assert response.status_code == expect, response.text
    return response.json()


# ----------------------------------------------------- registration gate ---

async def test_registration_gated_until_start(client):
    """Before ``registration_starts_at`` nobody gets a ticket — not via the
    bot path (create_ticket) and not as a staff walk-in; the event reports
    the ``announced`` phase. Once the moment passes, registration opens."""
    token, _ = await setup_company(client, desks=0)
    event = await create_event(client, token, reg_min=30)  # opens in 30 min
    assert (await get_event(client, token, event["id"]))["phase"] == "announced"

    async with SessionFactory() as db:
        ev = await db.get(SaleEvent, event["id"])
        assert ev.registration_pending() is True and ev.registration_open() is False
        try:
            await ticket_service.create_ticket(
                db, ev, first_name="Erta", last_name="Mijoz", phone="+998901000001"
            )
            message = None
        except DomainError as exc:
            message = exc.message
    assert message == "Ro'yxatdan o'tish hali boshlanmagan"

    walkin = await client.post(
        f"/api/queue/{event['id']}/walkin",
        json={"first_name": "Karim", "last_name": "Olimov", "phone": "+998905550001"},
        headers=auth(token),
    )
    assert walkin.status_code == 400

    # the opening moment passes → registration is open and stays open
    reg_open = (now_utc() - timedelta(minutes=1)).isoformat()
    updated = await client.patch(
        f"/api/events/{event['id']}",
        json={"registration_starts_at": reg_open},
        headers=auth(token),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["phase"] == "registration"
    ticket = await make_ticket(event["id"], "+998901000002", 0)
    assert re.fullmatch(r"[A-Z]{4}", ticket["number"])


# ------------------------------------------------------------ late group ---

async def test_late_scan_joins_last_queue(client):
    """Once open, registration never closes until the sale is deactivated or
    ends — but a QR scanned after the scanning window lands in the
    end-of-day queue."""
    token, _ = await setup_company(client, desks=0)
    # registration opened an hour ago; the scan window is open
    event = await create_event(client, token, reg_min=-60, starts_min=-10)

    early = await make_ticket(event["id"], "+998901000001", -3600)
    late_comer = await make_ticket(event["id"], "+998901000002", 0)

    early_result = await checkin(client, token, event["id"], early["number"])
    assert early_result["kind"] == "arrived" and early_result["ticket"]["late"] is False

    # the scanning window closes; the second client arrives only after that
    closed = (now_utc() - timedelta(seconds=1)).isoformat()
    moved = await client.patch(
        f"/api/events/{event['id']}", json={"checkin_until": closed}, headers=auth(token)
    )
    assert moved.status_code == 200, moved.text
    late_result = await checkin(client, token, event["id"], late_comer["number"])
    assert late_result["kind"] == "late" and late_result["ticket"]["late"] is True

    state = (await client.get(f"/api/events/{event['id']}/state", headers=auth(token))).json()
    waiting = [(t["number"], t["late"]) for t in state["waiting_list"]]
    assert waiting == [(early["number"], False), (late_comer["number"], True)]


# ----------------------------------------------------- sale lifecycle ---

async def test_sale_start_hold_resume_end_reopen(client):
    token, desk_ids = await setup_company(client, desks=1)
    event = await create_event(client, token)
    ticket = await make_ticket(event["id"], "+998901000001", -60)
    await checkin(client, token, event["id"], ticket["number"])

    # calling is blocked until sale_starts_at passes
    blocked = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert blocked.status_code == 400 and "boshlanmagan" in blocked.json()["detail"]

    await close_checkin_window(client, token, event["id"])
    assert (await get_event(client, token, event["id"]))["phase"] == "queue"

    # ON HOLD pauses calling; resume opens it exactly where it stopped
    held = await sale_action(client, token, event["id"], "hold")
    assert held["sale_hold"] is True and held["phase"] == "hold"
    paused = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert paused.status_code == 400 and "to'xtatib" in paused.json()["detail"]
    await sale_action(client, token, event["id"], "resume")
    called = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert called.status_code == 200 and called.json()["ticket"]["number"] == ticket["number"]

    # the owner ends the sale: no more scans, no more calls
    ended = await sale_action(client, token, event["id"], "end")
    assert ended["phase"] == "ended" and ended["sale_ended_at"] is not None
    dead_scan = await client.post(
        f"/api/queue/{event['id']}/checkin", json={"number": ticket["number"]}, headers=auth(token)
    )
    assert dead_scan.status_code == 400
    # ...and reopen brings it back
    reopened = await sale_action(client, token, event["id"], "reopen")
    assert reopened["phase"] == "queue" and reopened["sale_ended_at"] is None


async def test_sale_ends_automatically_when_queue_drains(client):
    token, desk_ids = await setup_company(client, desks=1)
    event = await create_event(client, token)
    ticket = await make_ticket(event["id"], "+998901000001", -60)
    await checkin(client, token, event["id"], ticket["number"])
    await close_checkin_window(client, token, event["id"])

    await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    for action in ("serving", "done"):
        response = await client.post(
            f"/api/queue/{event['id']}/{action}",
            json={"number": ticket["number"]},
            headers=auth(token),
        )
        assert response.status_code == 200, response.text

    after = await get_event(client, token, event["id"])
    assert after["phase"] == "ended" and after["sale_ended_at"] is not None


# ------------------------------------------------------------- walk-ins ---

async def test_walkin_goes_to_last_queue_and_shows_qr(client):
    token, _ = await setup_company(client, desks=0)
    event = await create_event(client, token)
    on_time = await make_ticket(event["id"], "+998901000001", -60)
    await checkin(client, token, event["id"], on_time["number"])

    added = await client.post(
        f"/api/queue/{event['id']}/walkin",
        json={"first_name": "Karim", "last_name": "Olimov", "phone": "+998905550001"},
        headers=auth(token),
    )
    assert added.status_code == 201, added.text
    body = added.json()
    assert body["qr"].startswith("data:image/png;base64,")
    assert re.fullmatch(r"[A-Z]{4}", body["ticket"]["number"])
    assert body["ticket"]["status"] == "checked_in"
    assert body["ticket"]["late"] is True and body["ticket"]["source"] == "staff"

    # the walk-in queues behind everyone already checked in
    state = (await client.get(f"/api/events/{event['id']}/state", headers=auth(token))).json()
    assert [t["number"] for t in state["waiting_list"]] == [
        on_time["number"],
        body["ticket"]["number"],
    ]
    assert state["stats"]["staff_added"] == 1 and state["stats"]["late"] == 1

    # one phone still means one ticket per event
    duplicate = await client.post(
        f"/api/queue/{event['id']}/walkin",
        json={"first_name": "Karim", "last_name": "Olimov", "phone": "+998905550001"},
        headers=auth(token),
    )
    assert duplicate.status_code == 409

    # the walk-in's QR is already used — scanning it changes nothing
    rescanned = await checkin(client, token, event["id"], body["ticket"]["number"])
    assert rescanned["ok"] is False and rescanned["kind"] == "already"


async def test_walkin_roles_scanner_yes_manager_no(client):
    token, _ = await setup_company(client, desks=0)
    event = await create_event(client, token)
    staff = {}
    for role, phone in (("scanner", "+998903333333"), ("manager", "+998904444444")):
        created = await client.post(
            "/api/employees",
            json={"first_name": role.title(), "phone": phone, "role": role},
            headers=auth(token),
        )
        login = await client.post(
            "/api/auth/login", json={"phone": phone, "password": created.json()["password"]}
        )
        staff[role] = login.json()["access_token"]

    ok = await client.post(
        f"/api/queue/{event['id']}/walkin",
        json={"first_name": "Aziz", "phone": "+998905550002"},
        headers=auth(staff["scanner"]),
    )
    assert ok.status_code == 201, ok.text
    forbidden = await client.post(
        f"/api/queue/{event['id']}/walkin",
        json={"first_name": "Aziz", "phone": "+998905550003"},
        headers=auth(staff["manager"]),
    )
    assert forbidden.status_code == 403


# ---------------------------------------------------------- sale outcome ---

async def test_done_records_contract_outcome_in_stats(client):
    """Finishing a client stores the manager's "contract signed?" answer; the
    counters reach the staff stats and the owner overview but never the
    public display payload."""
    token, desk_ids = await setup_company(client, desks=1)
    event = await create_event(client, token)
    numbers = []
    for i, offset in enumerate((-300, -200, -100)):
        ticket = await make_ticket(event["id"], f"+99890100000{i + 1}", offset)
        numbers.append(ticket["number"])
        await checkin(client, token, event["id"], ticket["number"])
    await close_checkin_window(client, token, event["id"])

    async def serve(number, extra):
        called = await client.post(
            f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
        )
        assert called.status_code == 200 and called.json()["ticket"]["number"] == number
        done = await client.post(
            f"/api/queue/{event['id']}/done",
            json={"number": number, **extra},
            headers=auth(token),
        )
        assert done.status_code == 200, done.text
        return done.json()

    first = await serve(numbers[0], {"contract_signed": True})
    assert first["ticket"]["contract_signed"] is True
    assert "shartnoma tuzildi" in first["message"]
    second = await serve(numbers[1], {"contract_signed": False})
    assert second["ticket"]["contract_signed"] is False
    assert "shartnoma tuzilmadi" in second["message"]
    # a caller that never asks the question leaves the outcome unrecorded
    third = await serve(numbers[2], {})
    assert third["ticket"]["contract_signed"] is None

    state = (await client.get(f"/api/events/{event['id']}/state", headers=auth(token))).json()
    assert state["stats"]["done"] == 3
    assert state["stats"]["contracts"] == 1
    assert state["stats"]["no_contract"] == 1

    # the public TV payload never carries the sale outcome
    display_code = (await get_event(client, token, event["id"]))["display_code"]
    public = (await client.get(f"/api/public/display/{display_code}")).json()
    assert "contracts" not in public["stats"] and "no_contract" not in public["stats"]

    overview = (await client.get("/api/stats/overview", headers=auth(token))).json()
    assert overview["totals"]["contracts"] == 1
    assert overview["totals"]["no_contract"] == 1
    assert overview["daily"][-1]["contracts"] == 1
    assert overview["events"][-1]["contracts"] == 1


# ------------------------------------------------- sale-start notifications ---

async def test_sale_start_burst_sends_position_and_ms_time_once(client, monkeypatch):
    token, _ = await setup_company(client, desks=0)
    event = await create_event(client, token)

    async with SessionFactory() as db:
        ev = await db.get(SaleEvent, event["id"])
        for i, chat in enumerate((501, 502)):
            ticket = await make_ticket(event["id"], f"+99890100000{i + 1}", -300 + i * 60)
            db_ticket = await db.get(Ticket, ticket["id"])
            db_ticket.telegram_chat_id = chat
            await db.commit()
            await checkin(client, token, event["id"], ticket["number"])

    await client.patch(
        f"/api/events/{event['id']}", json=started_sale_times(), headers=auth(token)
    )

    sent: list[tuple[int, str]] = []

    async def fake_send(company_id, chat_id, text, bot_id=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(notify, "send_telegram_text", fake_send)

    async with SessionFactory() as db:
        ev = await db.get(SaleEvent, event["id"])
        assert await queue_service.claim_sale_notification(db, ev.id) is True
        assert await queue_service.notify_sale_started(db, ev) == 2
        # the claim is one-shot: a second worker never re-sends the burst
        assert await queue_service.claim_sale_notification(db, ev.id) is False

    assert [chat for chat, _ in sent] == [501, 502]
    first, second = (text for _, text in sent)
    # each client sees their code, their bot registration time WITH
    # milliseconds, and how many people stand before them
    assert re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}", first)
    assert "0 kishi" in first and "1 kishi" in second


# ------------------------------------------------------- single-use QR ---

async def test_qr_is_single_use(client):
    token, _ = await setup_company(client, desks=0)
    event = await create_event(client, token)
    ticket = await make_ticket(event["id"], "+998901000001", -60)

    first = await checkin(client, token, event["id"], ticket["number"])
    assert first["ok"] is True and first["kind"] == "arrived"

    again = await checkin(client, token, event["id"], ticket["number"])
    assert again["ok"] is False and again["kind"] == "already"
    assert "QR allaqachon ishlatilgan" in again["message"]

    # the queue itself is untouched by the second scan
    async with SessionFactory() as db:
        row = await db.scalar(select(Ticket).where(Ticket.id == ticket["id"]))
        assert row.status.value == "checked_in"
        event_row = await db.get(SaleEvent, event["id"])
        assert event_row.late_seq == 0  # no late slot was burned
