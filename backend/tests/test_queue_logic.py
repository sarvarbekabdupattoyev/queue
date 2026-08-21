"""Core product rules: random 4-letter codes, the check-in window, and queue
order by bot registration time among checked-in tickets only."""

import re
from datetime import timedelta

from sqlalchemy import select

from app.db.base import now_utc
from app.db.session import SessionFactory
from app.models import SaleEvent, Ticket
from app.models.enums import TicketStatus
from app.services import queue_service, ticket_service
from tests.conftest import auth, create_company, event_times, register_owner, started_sale_times

NOW = now_utc


async def setup_company(client, desks: int = 2):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    desk_ids = []
    for n in range(1, desks + 1):
        desk = await client.post("/api/desks", json={"number": n}, headers=auth(token))
        desk_ids.append(desk.json()["id"])
    return token, desk_ids


async def create_event(client, token, **time_offsets):
    response = await client.post(
        "/api/events",
        json={"name": "Sotuv kuni", **event_times(**time_offsets)},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def make_ticket(event_id: int, phone: str, registered_offset_sec: int) -> dict:
    """Create a ticket via the service and pin its registration time."""
    async with SessionFactory() as db:
        event = await db.get(SaleEvent, event_id)
        ticket = await ticket_service.create_ticket(
            db,
            event,
            first_name="Mijoz",
            last_name=phone[-4:],
            phone=phone,
            telegram_chat_id=None,
        )
        ticket.registered_at = NOW() + timedelta(seconds=registered_offset_sec)
        await db.commit()
        return {"number": ticket.number, "code": ticket.code, "id": ticket.id}


async def close_checkin_window(client, token, event_id):
    """Move every period into the past: the scan window is over, the sale runs."""
    response = await client.patch(
        f"/api/events/{event_id}", json=started_sale_times(), headers=auth(token)
    )
    assert response.status_code == 200, response.text


async def test_numbers_are_random_unique_four_letter(client):
    token, _ = await setup_company(client, desks=0)
    event = await create_event(client, token)
    numbers = []
    for i in range(60):
        ticket = await make_ticket(event["id"], f"+9989012345{i:02d}", i)
        numbers.append(ticket["number"])
    assert all(re.fullmatch(r"[A-Z]{4}", n) for n in numbers)
    assert len(set(numbers)) == len(numbers)
    # not handed out in order
    assert numbers != sorted(numbers)


async def test_duplicate_phone_rejected(client):
    token, _ = await setup_company(client, desks=0)
    event = await create_event(client, token)
    await make_ticket(event["id"], "+998901111111", 0)
    async with SessionFactory() as db:
        ev = await db.get(SaleEvent, event["id"])
        try:
            await ticket_service.create_ticket(
                db, ev, first_name="A", last_name="B", phone="+998901111111"
            )
            raised = False
        except Exception:
            raised = True
    assert raised


async def test_checkin_and_queue_order_follows_registration_time(client):
    token, desk_ids = await setup_company(client)
    event = await create_event(client, token)

    # registration order (by time): t_b(-300s) < t_a(-200s) < t_c(-100s) < t_d(-50s)
    t_a = await make_ticket(event["id"], "+998901000001", -200)
    t_b = await make_ticket(event["id"], "+998901000002", -300)
    t_c = await make_ticket(event["id"], "+998901000003", -100)
    t_d = await make_ticket(event["id"], "+998901000004", -50)

    # check in c, then a (by code), then b — arrival order must NOT matter
    for ticket, payload in (
        (t_c, {"number": t_c["number"]}),
        (t_a, {"code": t_a["code"]}),
        (t_b, {"number": t_b["number"]}),
    ):
        response = await client.post(
            f"/api/queue/{event['id']}/checkin", json=payload, headers=auth(token)
        )
        assert response.status_code == 200, response.text
        assert response.json()["ok"] is True
        assert response.json()["kind"] == "arrived"

    # double check-in reports the position instead of duplicating
    again = await client.post(
        f"/api/queue/{event['id']}/checkin",
        json={"number": t_c["number"]},
        headers=auth(token),
    )
    assert again.json()["ok"] is False and again.json()["kind"] == "already"

    state = await client.get(f"/api/events/{event['id']}/state", headers=auth(token))
    waiting = [t["number"] for t in state.json()["waiting_list"]]
    assert waiting == [t_b["number"], t_a["number"], t_c["number"]]

    # queue has not started: calling is blocked
    call = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert call.status_code == 400

    await close_checkin_window(client, token, event["id"])

    # first call → earliest registration (t_b), regardless of scan order/number
    call = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert call.status_code == 200, call.text
    assert call.json()["ticket"]["number"] == t_b["number"]

    # same desk cannot call twice while busy
    busy = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert busy.status_code == 409

    # second desk → t_a
    call2 = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[1]}, headers=auth(token)
    )
    assert call2.json()["ticket"]["number"] == t_a["number"]

    # d checks in after the deadline → late group, joins the back
    late = await client.post(
        f"/api/queue/{event['id']}/checkin", json={"number": t_d["number"]}, headers=auth(token)
    )
    assert late.json()["kind"] == "late"
    state = await client.get(f"/api/events/{event['id']}/state", headers=auth(token))
    waiting = [(t["number"], t["late"]) for t in state.json()["waiting_list"]]
    assert waiting == [(t_c["number"], False), (t_d["number"], True)]

    # serve and finish t_b, then the desk frees up for t_c
    for action in ("serving", "done"):
        response = await client.post(
            f"/api/queue/{event['id']}/{action}",
            json={"number": t_b["number"]},
            headers=auth(token),
        )
        assert response.status_code == 200, response.text
    call3 = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert call3.json()["ticket"]["number"] == t_c["number"]


async def test_skip_returns_late_then_cancelled(client):
    token, desk_ids = await setup_company(client, desks=1)
    event = await create_event(client, token)
    t_a = await make_ticket(event["id"], "+998901000001", -100)
    t_b = await make_ticket(event["id"], "+998901000002", -50)
    for t in (t_a, t_b):
        await client.post(
            f"/api/queue/{event['id']}/checkin", json={"number": t["number"]}, headers=auth(token)
        )
    await close_checkin_window(client, token, event["id"])

    # call a, skip a → b becomes first; a re-checks in → goes behind b (late)
    await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    skip = await client.post(
        f"/api/queue/{event['id']}/skip", json={"number": t_a["number"]}, headers=auth(token)
    )
    assert skip.status_code == 200

    rejoin = await client.post(
        f"/api/queue/{event['id']}/checkin", json={"number": t_a["number"]}, headers=auth(token)
    )
    assert rejoin.json()["kind"] == "late"
    state = await client.get(f"/api/events/{event['id']}/state", headers=auth(token))
    waiting = [t["number"] for t in state.json()["waiting_list"]]
    assert waiting == [t_b["number"], t_a["number"]]

    # b done; a called again and skipped a second time → re-check-in cancels
    call = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert call.json()["ticket"]["number"] == t_b["number"]
    await client.post(
        f"/api/queue/{event['id']}/done", json={"number": t_b["number"]}, headers=auth(token)
    )
    call = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert call.json()["ticket"]["number"] == t_a["number"]
    await client.post(
        f"/api/queue/{event['id']}/skip", json={"number": t_a["number"]}, headers=auth(token)
    )
    final = await client.post(
        f"/api/queue/{event['id']}/checkin", json={"number": t_a["number"]}, headers=auth(token)
    )
    assert final.json()["kind"] == "cancelled"

    async with SessionFactory() as db:
        ticket = await db.scalar(select(Ticket).where(Ticket.id == t_a["id"]))
        assert ticket.status.value == "cancelled"


async def test_public_display_and_ticket_endpoints(client):
    token, desk_ids = await setup_company(client, desks=1)
    event = await create_event(client, token)
    ticket = await make_ticket(event["id"], "+998901000001", -10)
    await client.post(
        f"/api/queue/{event['id']}/checkin", json={"number": ticket["number"]}, headers=auth(token)
    )

    display = await client.get(f"/api/public/display/{event['display_code']}")
    assert display.status_code == 200
    body = display.json()
    # the board shows the letter code, the client's name and the bot
    # registration moment with milliseconds — but never phones or QR codes
    (entry,) = body["next"]
    assert entry["number"] == ticket["number"]
    assert entry["name"] == "Mijoz 0001"
    assert re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}", entry["registered_at"])
    assert entry["late"] is False
    assert "phone" not in entry and "code" not in entry
    assert "waiting_list" not in body  # staff-only payload stays staff-only
    assert body["stats"]["waiting"] == 1

    public_ticket = await client.get(f"/api/public/tickets/{ticket['code']}")
    assert public_ticket.status_code == 200
    # queue order is announced only once the sale starts
    assert public_ticket.json()["position"] is None
    assert public_ticket.json()["qr"].startswith("data:image/png;base64,")

    await close_checkin_window(client, token, event["id"])
    started = await client.get(f"/api/public/tickets/{ticket['code']}")
    assert started.json()["position"] == 1

    missing = await client.get("/api/public/display/nope")
    assert missing.status_code == 404


async def test_scanner_role_can_checkin_but_not_call(client):
    token, desk_ids = await setup_company(client, desks=1)
    event = await create_event(client, token)
    ticket = await make_ticket(event["id"], "+998901000001", 0)

    scanner = await client.post(
        "/api/employees",
        json={"first_name": "Skanner", "phone": "+998903333333", "role": "scanner"},
        headers=auth(token),
    )
    login = await client.post(
        "/api/auth/login",
        json={"phone": "+998903333333", "password": scanner.json()["password"]},
    )
    scanner_token = login.json()["access_token"]

    checkin = await client.post(
        f"/api/queue/{event['id']}/checkin",
        json={"code": ticket["code"]},
        headers=auth(scanner_token),
    )
    assert checkin.status_code == 200 and checkin.json()["ok"] is True

    await close_checkin_window(client, token, event["id"])
    call = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_ids[0]},
        headers=auth(scanner_token),
    )
    assert call.status_code == 403


async def test_events_isolated_between_companies(client):
    token1, _ = await setup_company(client, desks=0)
    event1 = await create_event(client, token1)

    token2 = (await register_owner(client, phone="+998907777777"))["access_token"]
    await create_company(client, token2, name="Boshqa Kompaniya")

    peek = await client.get(f"/api/events/{event1['id']}", headers=auth(token2))
    assert peek.status_code == 404
    poke = await client.post(
        f"/api/queue/{event1['id']}/checkin", json={"number": "ABCD"}, headers=auth(token2)
    )
    assert poke.status_code == 404


async def test_call_next_skips_a_ticket_another_desk_already_claimed(client, monkeypatch):
    """Two desks calling next at the same moment can both select the same
    waiting ticket before either claims it. Force that exact interleaving:
    let call_next pick t_a, then -- inside its own claim attempt -- have
    "desk 2" win the row out from under it and report the claim as lost.
    call_next must retry onto t_b, never overwrite desk 2's assignment."""
    token, desk_ids = await setup_company(client, desks=2)
    event = await create_event(client, token)
    t_a = await make_ticket(event["id"], "+998901000001", -100)
    t_b = await make_ticket(event["id"], "+998901000002", -50)
    for t in (t_a, t_b):
        await client.post(
            f"/api/queue/{event['id']}/checkin", json={"number": t["number"]}, headers=auth(token)
        )
    await close_checkin_window(client, token, event["id"])

    real_claim_status = queue_service._claim_status
    raced = {"done": False}

    async def claim_but_lose_the_first_race(db, ticket, expected, **values):
        if not raced["done"] and ticket.id == t_a["id"]:
            raced["done"] = True
            async with SessionFactory() as other_db:
                won_by_desk2 = await other_db.get(Ticket, t_a["id"])
                won_by_desk2.status = TicketStatus.CALLED
                won_by_desk2.desk_id = desk_ids[1]
                won_by_desk2.called_at = now_utc()
                won_by_desk2.call_count += 1
                await other_db.commit()
            return False
        return await real_claim_status(db, ticket, expected, **values)

    monkeypatch.setattr(queue_service, "_claim_status", claim_but_lose_the_first_race)

    call = await client.post(
        f"/api/queue/{event['id']}/call", json={"desk_id": desk_ids[0]}, headers=auth(token)
    )
    assert call.status_code == 200, call.text
    assert call.json()["ticket"]["number"] == t_b["number"]

    async with SessionFactory() as db:
        claimed_by_desk2 = await db.get(Ticket, t_a["id"])
        assert claimed_by_desk2.desk_id == desk_ids[1]
        assert claimed_by_desk2.call_count == 1
