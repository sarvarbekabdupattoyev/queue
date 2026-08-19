"""Branch ("filial") rules: one event in many branches, branch-scoped
managers/desks/queues, and the multi-bot (up to 3) company setup."""

from datetime import timedelta

from app.db.base import now_utc
from app.db.session import SessionFactory
from app.models import SaleEvent
from app.services import ticket_service
from app.services.errors import DomainError
from tests.conftest import auth, create_company, register_owner

NOW = now_utc


async def make_branch(client, token, name: str, address: str = "") -> dict:
    response = await client.post(
        "/api/branches", json={"name": name, "address": address}, headers=auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def make_event(client, token, branch_ids: list[int], **kw) -> dict:
    response = await client.post(
        "/api/events",
        json={
            "name": kw.get("name", "Sotuv kuni"),
            "starts_at": (NOW() - timedelta(minutes=60)).isoformat(),
            "checkin_until": (NOW() + timedelta(minutes=60)).isoformat(),
            "branch_ids": branch_ids,
        },
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def make_ticket(
    event_id: int, phone: str, registered_offset_sec: int, branch_id: int | None = None
) -> dict:
    async with SessionFactory() as db:
        event = await db.get(SaleEvent, event_id)
        ticket = await ticket_service.create_ticket(
            db,
            event,
            first_name="Mijoz",
            last_name=phone[-4:],
            phone=phone,
            branch_id=branch_id,
        )
        ticket.registered_at = NOW() + timedelta(seconds=registered_offset_sec)
        await db.commit()
        return {"number": ticket.number, "code": ticket.code, "id": ticket.id}


async def close_checkin(client, token, event_id) -> None:
    response = await client.patch(
        f"/api/events/{event_id}",
        json={
            "starts_at": (NOW() - timedelta(hours=3)).isoformat(),
            "checkin_until": (NOW() - timedelta(seconds=1)).isoformat(),
        },
        headers=auth(token),
    )
    assert response.status_code == 200, response.text


async def test_branch_crud_and_tenancy(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch = await make_branch(client, token, "Chilonzor", "Toshkent, Chilonzor")

    # duplicate name inside one company
    dup = await client.post("/api/branches", json={"name": "Chilonzor"}, headers=auth(token))
    assert dup.status_code == 409

    renamed = await client.patch(
        f"/api/branches/{branch['id']}", json={"name": "Yunusobod"}, headers=auth(token)
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Yunusobod"

    # a second company can neither see nor touch it
    token2 = (await register_owner(client, phone="+998907777777"))["access_token"]
    await create_company(client, token2, name="Boshqa")
    assert (await client.get("/api/branches", headers=auth(token2))).json() == []
    foreign = await client.patch(
        f"/api/branches/{branch['id']}", json={"name": "Begona"}, headers=auth(token2)
    )
    assert foreign.status_code == 404


async def test_one_event_runs_in_many_branches_with_separate_queues(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch_a = await make_branch(client, token, "Chilonzor")
    branch_b = await make_branch(client, token, "Sergeli")
    event = await make_event(client, token, [branch_a["id"], branch_b["id"]])
    assert {b["name"] for b in event["branches"]} == {"Chilonzor", "Sergeli"}

    desk_a = await client.post(
        "/api/desks", json={"number": 1, "branch_id": branch_a["id"]}, headers=auth(token)
    )
    desk_b = await client.post(
        "/api/desks", json={"number": 1, "branch_id": branch_b["id"]}, headers=auth(token)
    )
    # same desk number is fine in different branches
    assert desk_a.status_code == 201 and desk_b.status_code == 201, desk_b.text

    # registration order: b1(-300) < a1(-200) < a2(-100) < b2(-50)
    t_a1 = await make_ticket(event["id"], "+998901000001", -200, branch_a["id"])
    t_a2 = await make_ticket(event["id"], "+998901000002", -100, branch_a["id"])
    t_b1 = await make_ticket(event["id"], "+998901000003", -300, branch_b["id"])
    t_b2 = await make_ticket(event["id"], "+998901000004", -50, branch_b["id"])

    for t in (t_a2, t_b2, t_a1, t_b1):  # scan order must not matter
        response = await client.post(
            f"/api/queue/{event['id']}/checkin", json={"number": t["number"]}, headers=auth(token)
        )
        assert response.json()["ok"] is True, response.text

    # per-branch waiting lists in the staff state, ordered by registration
    state = (await client.get(f"/api/events/{event['id']}/state", headers=auth(token))).json()
    per_branch = {
        branch_id: [t["number"] for t in state["waiting_list"] if t["branch_id"] == branch_id]
        for branch_id in (branch_a["id"], branch_b["id"])
    }
    assert per_branch[branch_a["id"]] == [t_a1["number"], t_a2["number"]]
    assert per_branch[branch_b["id"]] == [t_b1["number"], t_b2["number"]]
    by_branch = {s["id"]: s for s in state["by_branch"]}
    next_a = [entry["number"] for entry in by_branch[branch_a["id"]]["next"]]
    assert next_a == [t_a1["number"], t_a2["number"]]
    assert by_branch[branch_b["id"]]["stats"]["waiting"] == 2

    # positions are branch-local: b2 is 2nd in Sergeli even though 3 people
    # registered earlier overall
    ticket_page = await client.get(f"/api/public/tickets/{t_b2['code']}")
    assert ticket_page.json()["position"] == 2
    assert ticket_page.json()["waiting_count"] == 2
    assert ticket_page.json()["branch_name"] == "Sergeli"

    await close_checkin(client, token, event["id"])

    # each desk pulls from ITS branch queue only
    call_a = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_a.json()["id"]},
        headers=auth(token),
    )
    assert call_a.json()["ticket"]["number"] == t_a1["number"]
    call_b = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_b.json()["id"]},
        headers=auth(token),
    )
    assert call_b.json()["ticket"]["number"] == t_b1["number"]

    # a desk without a branch cannot serve a multi-branch event
    free_desk = await client.post("/api/desks", json={"number": 7}, headers=auth(token))
    no_branch_call = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": free_desk.json()["id"]},
        headers=auth(token),
    )
    assert no_branch_call.status_code == 400


async def test_branch_event_requires_branch_on_registration(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch = await make_branch(client, token, "Chilonzor")
    event = await make_event(client, token, [branch["id"]])

    async with SessionFactory() as db:
        ev = await db.get(SaleEvent, event["id"])
        for bad_branch in (None, branch["id"] + 999):
            try:
                await ticket_service.create_ticket(
                    db, ev, first_name="A", last_name="B", phone="+998901111111",
                    branch_id=bad_branch,
                )
                raised = False
            except DomainError:
                raised = True
            assert raised, f"branch_id={bad_branch} must be rejected"


async def test_branch_staff_cannot_cross_branches(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch_a = await make_branch(client, token, "Chilonzor")
    branch_b = await make_branch(client, token, "Sergeli")
    event = await make_event(client, token, [branch_a["id"], branch_b["id"]])

    desk_b = await client.post(
        "/api/desks", json={"number": 1, "branch_id": branch_b["id"]}, headers=auth(token)
    )
    scanner = await client.post(
        "/api/employees",
        json={
            "first_name": "Skanner", "phone": "+998903333333",
            "role": "scanner", "branch_id": branch_a["id"],
        },
        headers=auth(token),
    )
    manager = await client.post(
        "/api/employees",
        json={
            "first_name": "Menejer", "phone": "+998904444444",
            "role": "manager", "branch_id": branch_a["id"],
        },
        headers=auth(token),
    )
    assert scanner.json()["employee"]["branch_id"] == branch_a["id"]

    # a manager of branch A cannot be attached to a branch-B desk
    mismatch = await client.patch(
        f"/api/desks/{desk_b.json()['id']}",
        json={"manager_id": manager.json()["employee"]["id"]},
        headers=auth(token),
    )
    assert mismatch.status_code == 400

    ticket_b = await make_ticket(event["id"], "+998901000009", -10, branch_b["id"])

    async def login(created):
        response = await client.post(
            "/api/auth/login",
            json={"phone": created.json()["employee"]["phone"], "password": created.json()["password"]},
        )
        return response.json()["access_token"]

    scanner_token = await login(scanner)
    manager_token = await login(manager)

    # branch-A scanner cannot check in a branch-B client
    wrong = await client.post(
        f"/api/queue/{event['id']}/checkin",
        json={"number": ticket_b["number"]},
        headers=auth(scanner_token),
    )
    assert wrong.status_code == 400
    assert "Sergeli" in wrong.json()["detail"]

    # branch-A manager cannot call at a branch-B desk
    await close_checkin(client, token, event["id"])
    call = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_b.json()["id"]},
        headers=auth(manager_token),
    )
    assert call.status_code == 403


async def test_branch_manager_cannot_act_on_another_branch_ticket(client):
    """Calling is branch-scoped; so are the per-ticket actions that follow it."""
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch_a = await make_branch(client, token, "Chilonzor")
    branch_b = await make_branch(client, token, "Sergeli")
    event = await make_event(client, token, [branch_a["id"], branch_b["id"]])
    desk_b = await client.post(
        "/api/desks", json={"number": 1, "branch_id": branch_b["id"]}, headers=auth(token)
    )
    manager_a = await client.post(
        "/api/employees",
        json={
            "first_name": "Menejer", "phone": "+998904444444",
            "role": "manager", "branch_id": branch_a["id"],
        },
        headers=auth(token),
    )
    login = await client.post(
        "/api/auth/login",
        json={"phone": "+998904444444", "password": manager_a.json()["password"]},
    )
    manager_token = login.json()["access_token"]

    ticket_b = await make_ticket(event["id"], "+998901000021", -60, branch_b["id"])
    await client.post(
        f"/api/queue/{event['id']}/checkin",
        json={"number": ticket_b["number"]},
        headers=auth(token),
    )
    await close_checkin(client, token, event["id"])
    called = await client.post(
        f"/api/queue/{event['id']}/call",
        json={"desk_id": desk_b.json()["id"]},
        headers=auth(token),
    )
    assert called.json()["ticket"]["number"] == ticket_b["number"]

    # the branch-A manager must not touch a branch-B client at any step
    for action in ("recall", "serving", "skip", "done"):
        response = await client.post(
            f"/api/queue/{event['id']}/{action}",
            json={"number": ticket_b["number"]},
            headers=auth(manager_token),
        )
        assert response.status_code == 403, f"{action} leaked across branches"

    # the owner (no branch) still can
    assert (
        await client.post(
            f"/api/queue/{event['id']}/serving",
            json={"number": ticket_b["number"]},
            headers=auth(token),
        )
    ).status_code == 200


async def test_cannot_add_branches_to_event_with_unscoped_tickets(client):
    """Tickets registered before branches exist carry no branch, so no desk
    could ever call them — adding branches later must be refused."""
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch = await make_branch(client, token, "Chilonzor")
    event = await make_event(client, token, [])  # unscoped event
    await make_ticket(event["id"], "+998901000031", -60, None)

    blocked = await client.patch(
        f"/api/events/{event['id']}",
        json={"branch_ids": [branch["id"]]},
        headers=auth(token),
    )
    assert blocked.status_code == 400
    assert "filialsiz" in blocked.json()["detail"]

    # an event with no tickets yet can still gain branches
    empty_event = await make_event(client, token, [], name="Bo'sh tadbir")
    ok = await client.patch(
        f"/api/events/{empty_event['id']}",
        json={"branch_ids": [branch["id"]]},
        headers=auth(token),
    )
    assert ok.status_code == 200
    assert [b["name"] for b in ok.json()["branches"]] == ["Chilonzor"]


async def test_event_branch_validation_and_removal_guard(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    branch = await make_branch(client, token, "Chilonzor")

    # foreign/unknown branch id is rejected at event creation
    bad = await client.post(
        "/api/events",
        json={
            "name": "Sotuv",
            "starts_at": (NOW() - timedelta(minutes=5)).isoformat(),
            "checkin_until": (NOW() + timedelta(minutes=60)).isoformat(),
            "branch_ids": [branch["id"] + 999],
        },
        headers=auth(token),
    )
    assert bad.status_code == 400

    event = await make_event(client, token, [branch["id"]])
    await make_ticket(event["id"], "+998901000001", 0, branch["id"])

    # the branch already holds tickets → cannot be detached from the event
    detach = await client.patch(
        f"/api/events/{event['id']}", json={"branch_ids": []}, headers=auth(token)
    )
    assert detach.status_code == 400

    # ...and cannot be deleted while wired into an active event
    delete = await client.delete(f"/api/branches/{branch['id']}", headers=auth(token))
    assert delete.status_code == 409

    # closing the event frees the branch
    await client.patch(
        f"/api/events/{event['id']}", json={"is_active": False}, headers=auth(token)
    )
    gone = await client.delete(f"/api/branches/{branch['id']}", headers=auth(token))
    assert gone.status_code == 204


async def test_company_connects_up_to_three_bots(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)

    bot_ids = []
    for i in range(2):
        response = await client.post(
            "/api/company/bots",
            json={"token": f"12345678{i}:TEST-TOKEN-{i}"},
            headers=auth(token),
        )
        assert response.status_code == 201, response.text
        bot_ids.append(response.json()["id"])

    # the same token cannot be connected twice (unique constraint, not count)
    duplicate = await client.post(
        "/api/company/bots", json={"token": "123456780:TEST-TOKEN-0"}, headers=auth(token)
    )
    assert duplicate.status_code == 409

    third = await client.post(
        "/api/company/bots", json={"token": "123456782:TEST-TOKEN-2"}, headers=auth(token)
    )
    assert third.status_code == 201
    bot_ids.append(third.json()["id"])

    fourth = await client.post(
        "/api/company/bots", json={"token": "999999999:TEST-TOKEN-9"}, headers=auth(token)
    )
    assert fourth.status_code == 409

    company = (await client.get("/api/company", headers=auth(token))).json()
    assert len(company["bots"]) == 3
    assert company["max_bots"] == 3
    assert company["has_bot_token"] is True

    dropped = await client.delete(f"/api/company/bots/{bot_ids[0]}", headers=auth(token))
    assert dropped.status_code == 204
    company = (await client.get("/api/company", headers=auth(token))).json()
    assert len(company["bots"]) == 2

    # another company cannot delete our bot
    token2 = (await register_owner(client, phone="+998907777777"))["access_token"]
    await create_company(client, token2, name="Boshqa")
    foreign = await client.delete(f"/api/company/bots/{bot_ids[1]}", headers=auth(token2))
    assert foreign.status_code == 404
