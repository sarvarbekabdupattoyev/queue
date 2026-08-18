"""Branches (optional, one bot for all of them) and the owner stats overview."""

from datetime import timedelta

from app.db.base import now_utc
from tests.conftest import auth, create_company, register_owner

NOW = now_utc


async def make_event(client, token, *, branch_id=None, name="Sotuv kuni"):
    payload = {
        "name": name,
        "starts_at": (NOW() - timedelta(minutes=60)).isoformat(),
        "checkin_until": (NOW() + timedelta(minutes=60)).isoformat(),
    }
    if branch_id is not None:
        payload["branch_id"] = branch_id
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
    branch = (
        await client.post("/api/branches", json={"name": "Sergeli"}, headers=auth(token))
    ).json()

    event = await make_event(client, token, branch_id=branch["id"])
    assert event["branch_id"] == branch["id"]
    assert event["branch_name"] == "Sergeli"

    cleared = await client.patch(
        f"/api/events/{event['id']}", json={"clear_branch": True}, headers=auth(token)
    )
    assert cleared.json()["branch_name"] is None

    reassigned = await client.patch(
        f"/api/events/{event['id']}", json={"branch_id": branch["id"]}, headers=auth(token)
    )
    assert reassigned.json()["branch_name"] == "Sergeli"

    # a branch of another company must not attach (400, not silently accepted)
    other = (await register_owner(client, phone="+998907654321"))["access_token"]
    await create_company(client, other, name="Boshqa MChJ")
    foreign = (
        await client.post("/api/branches", json={"name": "Begona"}, headers=auth(other))
    ).json()
    rejected = await client.patch(
        f"/api/events/{event['id']}", json={"branch_id": foreign["id"]}, headers=auth(token)
    )
    assert rejected.status_code == 400

    # deleting the branch keeps the event, just unlabelled
    await client.delete(f"/api/branches/{branch['id']}", headers=auth(token))
    refreshed = await client.get(f"/api/events/{event['id']}", headers=auth(token))
    assert refreshed.status_code == 200
    assert refreshed.json()["branch_name"] is None


async def test_stats_overview_counts_and_roles(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch = (
        await client.post("/api/branches", json={"name": "Markaz"}, headers=auth(token))
    ).json()
    event = await make_event(client, token, branch_id=branch["id"])

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

    stats = await client.get("/api/stats/overview", headers=auth(token))
    assert stats.status_code == 200, stats.text
    data = stats.json()
    assert data["days"] == 14
    assert data["totals"]["registered"] == 5
    assert data["totals"]["arrived"] == 2
    assert data["totals"]["served"] == 0
    assert data["totals"]["events"] == 1
    assert len(data["daily"]) == 14
    assert data["daily"][-1]["registered"] == 5
    assert data["daily"][-1]["arrived"] == 2
    assert sum(h["registered"] for h in data["hourly"]) == 5
    assert data["events"][-1]["id"] == event["id"]
    assert data["events"][-1]["registered"] == 5
    assert data["events"][-1]["branch_name"] == "Markaz"
    assert data["branches"] == [
        {
            "id": branch["id"],
            "name": "Markaz",
            "events": 1,
            "registered": 5,
            "arrived": 2,
            "served": 0,
        }
    ]

    # window bounds are validated
    assert (
        await client.get("/api/stats/overview?days=3", headers=auth(token))
    ).status_code == 422

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
