"""Branches (optional; one event may run in several) and the owner stats
overview."""

from datetime import timedelta

from app.db.base import now_utc
from app.db.session import SessionFactory
from app.models import SaleEvent
from app.services import ticket_service
from tests.conftest import auth, create_company, event_times, register_owner

NOW = now_utc


async def make_event(client, token, *, branch_ids=None, name="Sotuv kuni"):
    payload = {"name": name, **event_times(), "branch_ids": branch_ids or []}
    response = await client.post("/api/events", json=payload, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()


async def test_branch_crud_and_tenant_isolation(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)

    created = await client.post(
        "/api/branches",
        json={"name": "Chilonzor", "address": "Toshkent, Chilonzor 9"},
        headers=auth(token),
    )
    assert created.status_code == 201, created.text
    branch = created.json()
    assert branch["name"] == "Chilonzor"

    listed = await client.get("/api/branches", headers=auth(token))
    assert [b["id"] for b in listed.json()] == [branch["id"]]

    patched = await client.patch(
        f"/api/branches/{branch['id']}", json={"name": "Yunusobod"}, headers=auth(token)
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Yunusobod"

    dup = await client.post("/api/branches", json={"name": "Yunusobod"}, headers=auth(token))
    assert dup.status_code == 409

    # another tenant: list is empty, foreign branch reads as missing (404)
    other = (await register_owner(client, phone="+998907654321"))["access_token"]
    await create_company(client, other, name="Boshqa MChJ")
    assert (await client.get("/api/branches", headers=auth(other))).json() == []
    for response in (
        await client.patch(
            f"/api/branches/{branch['id']}", json={"name": "Xorazm"}, headers=auth(other)
        ),
        await client.delete(f"/api/branches/{branch['id']}", headers=auth(other)),
    ):
        assert response.status_code == 404

    deleted = await client.delete(f"/api/branches/{branch['id']}", headers=auth(token))
    assert deleted.status_code == 204


async def test_event_branch_assignment(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    sergeli = (
        await client.post("/api/branches", json={"name": "Sergeli"}, headers=auth(token))
    ).json()
    chilonzor = (
        await client.post("/api/branches", json={"name": "Chilonzor"}, headers=auth(token))
    ).json()

    # one event runs in SEVERAL branches at once
    event = await make_event(client, token, branch_ids=[sergeli["id"], chilonzor["id"]])
    assert [b["name"] for b in event["branches"]] == ["Sergeli", "Chilonzor"]

    cleared = await client.patch(
        f"/api/events/{event['id']}", json={"branch_ids": []}, headers=auth(token)
    )
    assert cleared.json()["branches"] == []

    reassigned = await client.patch(
        f"/api/events/{event['id']}", json={"branch_ids": [sergeli["id"]]}, headers=auth(token)
    )
    assert [b["name"] for b in reassigned.json()["branches"]] == ["Sergeli"]

    # a branch of another company must not attach (400, not silently accepted)
    other = (await register_owner(client, phone="+998907654321"))["access_token"]
    await create_company(client, other, name="Boshqa MChJ")
    foreign = (
        await client.post("/api/branches", json={"name": "Begona"}, headers=auth(other))
    ).json()
    rejected = await client.patch(
        f"/api/events/{event['id']}", json={"branch_ids": [foreign["id"]]}, headers=auth(token)
    )
    assert rejected.status_code == 400

    # a branch wired into an ACTIVE event is protected from deletion
    guarded = await client.delete(f"/api/branches/{sergeli['id']}", headers=auth(token))
    assert guarded.status_code == 409
    # closing the event releases it
    await client.patch(
        f"/api/events/{event['id']}", json={"is_active": False}, headers=auth(token)
    )
    assert (
        await client.delete(f"/api/branches/{sergeli['id']}", headers=auth(token))
    ).status_code == 204
    refreshed = await client.get(f"/api/events/{event['id']}", headers=auth(token))
    assert refreshed.status_code == 200
    assert refreshed.json()["branches"] == []


async def test_stats_overview_counts_and_roles(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch = (
        await client.post("/api/branches", json={"name": "Markaz"}, headers=auth(token))
    ).json()
    event = await make_event(client, token, branch_ids=[branch["id"]])

    seeded = (
        await client.post(f"/api/events/{event['id']}/seed", json={"count": 5}, headers=auth(token))
    ).json()
    assert len(seeded) == 5
    for ticket in seeded[:2]:
        checked = await client.post(
            f"/api/queue/{event['id']}/checkin",
            json={"number": ticket["number"]},
            headers=auth(token),
        )
        assert checked.status_code == 200, checked.text

    # registered long before the window, arrives today: must count as arrived
    # (not as registered) — registration opens weeks before the sale day
    async with SessionFactory() as db:
        db_event = await db.get(SaleEvent, event["id"])
        early = await ticket_service.create_ticket(
            db,
            db_event,
            first_name="Erta",
            last_name="Mijoz",
            phone="+998909999999",
            branch_id=branch["id"],
        )
        early.registered_at = NOW() - timedelta(days=30)
        await db.commit()
        early_number = early.number
    checked = await client.post(
        f"/api/queue/{event['id']}/checkin",
        json={"number": early_number},
        headers=auth(token),
    )
    assert checked.status_code == 200, checked.text

    stats = await client.get("/api/stats/overview", headers=auth(token))
    assert stats.status_code == 200, stats.text
    data = stats.json()
    assert data["days"] == 14
    assert data["totals"]["registered"] == 5
    assert data["totals"]["arrived"] == 3
    assert data["totals"]["served"] == 0
    assert data["totals"]["events"] == 1
    assert len(data["daily"]) == 14
    assert data["daily"][-1]["registered"] == 5
    assert data["daily"][-1]["arrived"] == 3
    assert sum(h["registered"] for h in data["hourly"]) == 5
    assert data["events"][-1]["id"] == event["id"]
    # the per-event list is all-time, so the early registration counts there
    assert data["events"][-1]["registered"] == 6
    assert data["events"][-1]["branch_names"] == ["Markaz"]
    assert data["branches"] == [
        {
            "id": branch["id"],
            "name": "Markaz",
            "events": 1,
            "registered": 5,
            "arrived": 3,
            "served": 0,
        }
    ]

    # window bounds are validated
    assert (
        await client.get("/api/stats/overview?days=3", headers=auth(token))
    ).status_code == 422

    # a brand-new company has no events at all — the aggregates must still build
    fresh = (await register_owner(client, phone="+998905550011"))["access_token"]
    await create_company(client, fresh, name="Yangi MChJ")
    empty = await client.get("/api/stats/overview", headers=auth(fresh))
    assert empty.status_code == 200, empty.text
    assert empty.json()["totals"]["events"] == 0
    assert empty.json()["events"] == [] and empty.json()["branches"] == []

    # stats are the owner's: a manager is refused, though they may read branches
    manager = (
        await client.post(
            "/api/employees",
            json={
                "first_name": "Menejer",
                "last_name": "Test",
                "phone": "+998901112233",
                "role": "manager",
            },
            headers=auth(token),
        )
    ).json()
    login = await client.post(
        "/api/auth/login",
        json={"phone": "+998901112233", "password": manager["password"]},
    )
    manager_token = login.json()["access_token"]
    assert (
        await client.get("/api/stats/overview", headers=auth(manager_token))
    ).status_code == 403
    assert (await client.get("/api/branches", headers=auth(manager_token))).status_code == 200
