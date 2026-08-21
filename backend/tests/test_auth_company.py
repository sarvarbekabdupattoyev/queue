from tests.conftest import auth, create_company, register_owner


async def test_register_login_me(client):
    data = await register_owner(client)
    assert data["user"]["role"] == "owner"
    assert data["user"]["phone"] == "+998901234567"

    login = await client.post(
        "/api/auth/login", json={"phone": "998901234567", "password": "secret123"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.get("/api/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["first_name"] == "Sarvar"


async def test_register_duplicate_phone(client):
    await register_owner(client)
    response = await client.post(
        "/api/auth/register",
        json={"first_name": "Aziz", "phone": "+998901234567", "password": "secret123"},
    )
    assert response.status_code == 409


async def test_login_wrong_password(client):
    await register_owner(client)
    response = await client.post(
        "/api/auth/login", json={"phone": "+998901234567", "password": "wrong"}
    )
    assert response.status_code == 401


async def test_invalid_phone_rejected(client):
    response = await client.post(
        "/api/auth/register",
        json={"first_name": "Aziz", "phone": "12345", "password": "secret123"},
    )
    assert response.status_code == 422


async def test_company_lifecycle(client):
    token = (await register_owner(client))["access_token"]
    company = await create_company(client, token)
    assert company["name"] == "Bahor City"
    # seeded from the operator's CALL_TIMEOUT_MINUTES default (3 in tests);
    # from here it is entirely the owner's to change
    assert company["call_timeout_minutes"] == 3

    # only one company per owner
    again = await client.post("/api/company", json={"name": "X Corp"}, headers=auth(token))
    assert again.status_code == 409

    renamed = await client.patch(
        "/api/company",
        json={"name": "Bahor City Group", "call_timeout_minutes": 10},
        headers=auth(token),
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Bahor City Group"
    assert renamed.json()["call_timeout_minutes"] == 10

    out_of_range = await client.patch(
        "/api/company", json={"call_timeout_minutes": 0}, headers=auth(token)
    )
    assert out_of_range.status_code == 422
    still = await client.get("/api/company", headers=auth(token))
    assert still.json()["call_timeout_minutes"] == 10  # rejected value never applied

    phone = await client.post(
        "/api/company/phones",
        json={"phone": "+998712005050", "label": "Call-markaz"},
        headers=auth(token),
    )
    assert phone.status_code == 201
    location = await client.post(
        "/api/company/locations",
        json={"name": "Bosh ofis", "address": "Toshkent, Yunusobod 4-mavze"},
        headers=auth(token),
    )
    assert location.status_code == 201

    got = await client.get("/api/company", headers=auth(token))
    body = got.json()
    assert len(body["phones"]) == 1 and len(body["locations"]) == 1
    assert body["has_bot_token"] is False

    dropped = await client.delete(
        f"/api/company/phones/{phone.json()['id']}", headers=auth(token)
    )
    assert dropped.status_code == 204


async def test_employee_lifecycle_and_roles(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)

    created = await client.post(
        "/api/employees",
        json={
            "first_name": "Malika",
            "last_name": "Yusupova",
            "phone": "+998909998877",
            "role": "manager",
        },
        headers=auth(token),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    password = body["password"]
    assert len(password) >= 8
    assert body["employee"]["role"] == "manager"

    # employee can log in with the generated password
    login = await client.post(
        "/api/auth/login", json={"phone": "+998909998877", "password": password}
    )
    assert login.status_code == 200
    employee_token = login.json()["access_token"]

    # ...but cannot manage employees
    forbidden = await client.get("/api/employees", headers=auth(employee_token))
    assert forbidden.status_code == 403

    # password reset invalidates the old password
    reset = await client.post(
        f"/api/employees/{body['employee']['id']}/reset-password", headers=auth(token)
    )
    assert reset.status_code == 200
    new_password = reset.json()["password"]
    assert new_password != password
    old_login = await client.post(
        "/api/auth/login", json={"phone": "+998909998877", "password": password}
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/auth/login", json={"phone": "+998909998877", "password": new_password}
    )
    assert new_login.status_code == 200

    # owner role is not a valid employee role
    invalid = await client.post(
        "/api/employees",
        json={"first_name": "Test", "phone": "+998901112233", "role": "owner"},
        headers=auth(token),
    )
    assert invalid.status_code == 400

    # deactivated employee cannot log in
    deactivated = await client.patch(
        f"/api/employees/{body['employee']['id']}",
        json={"is_active": False},
        headers=auth(token),
    )
    assert deactivated.status_code == 200
    blocked = await client.post(
        "/api/auth/login", json={"phone": "+998909998877", "password": new_password}
    )
    assert blocked.status_code == 403


async def test_employee_full_edit_including_phone(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    created = await client.post(
        "/api/employees",
        json={"first_name": "Malika", "last_name": "Yusupova", "phone": "+998909998877", "role": "manager"},
        headers=auth(token),
    )
    employee_id = created.json()["employee"]["id"]
    password = created.json()["password"]
    other = await client.post(
        "/api/employees",
        json={"first_name": "Aziz", "phone": "+998901112233", "role": "scanner"},
        headers=auth(token),
    )
    assert other.status_code == 201

    # the owner can change ANY field, phone included
    updated = await client.patch(
        f"/api/employees/{employee_id}",
        json={"first_name": "Madina", "last_name": "Karimova", "phone": "+998905554433", "role": "scanner"},
        headers=auth(token),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert (body["first_name"], body["last_name"], body["phone"], body["role"]) == (
        "Madina", "Karimova", "+998905554433", "scanner",
    )

    # login follows the phone: the new one works, the old one is gone
    assert (
        await client.post("/api/auth/login", json={"phone": "+998905554433", "password": password})
    ).status_code == 200
    assert (
        await client.post("/api/auth/login", json={"phone": "+998909998877", "password": password})
    ).status_code == 401

    # a phone already used inside the company is rejected
    conflict = await client.patch(
        f"/api/employees/{employee_id}", json={"phone": "+998901112233"}, headers=auth(token)
    )
    assert conflict.status_code == 409
    invalid = await client.patch(
        f"/api/employees/{employee_id}", json={"phone": "+7 900 000 00 00"}, headers=auth(token)
    )
    assert invalid.status_code == 422


async def test_same_employee_phone_allowed_across_companies(client):
    """A phone is unique inside ONE company: two different clients (companies)
    may each add the same person as their manager."""
    token1 = (await register_owner(client))["access_token"]
    company1 = await create_company(client, token1)
    token2 = (await register_owner(client, phone="+998907777777"))["access_token"]
    company2 = await create_company(client, token2, name="Boshqa Kompaniya")

    manager = {"first_name": "Malika", "last_name": "Yusupova", "phone": "+998909998877", "role": "manager"}
    first = await client.post("/api/employees", json=manager, headers=auth(token1))
    assert first.status_code == 201, first.text

    # the same phone in ANOTHER company must be accepted
    second = await client.post("/api/employees", json=manager, headers=auth(token2))
    assert second.status_code == 201, second.text

    # ...but stays unique inside one company
    duplicate = await client.post("/api/employees", json=manager, headers=auth(token2))
    assert duplicate.status_code == 409

    # each account logs in with its own password and lands in its own company
    for response, company in ((first, company1), (second, company2)):
        login = await client.post(
            "/api/auth/login",
            json={"phone": "+998909998877", "password": response.json()["password"]},
        )
        assert login.status_code == 200, login.text
        assert login.json()["user"]["company_id"] == company["id"]


async def test_owner_can_register_with_phone_employed_elsewhere(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    employee = await client.post(
        "/api/employees",
        json={"first_name": "Malika", "phone": "+998909998877", "role": "manager"},
        headers=auth(token),
    )
    assert employee.status_code == 201

    # being someone's manager must not block signing up as a new client
    signup = await register_owner(client, phone="+998909998877")
    assert signup["user"]["role"] == "owner"

    # duplicate owner accounts are still rejected
    again = await client.post(
        "/api/auth/register",
        json={"first_name": "Aziz", "phone": "+998909998877", "password": "secret123"},
    )
    assert again.status_code == 409


async def test_desks(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    scanner = await client.post(
        "/api/employees",
        json={"first_name": "Skanner", "phone": "+998901111111", "role": "scanner"},
        headers=auth(token),
    )
    manager = await client.post(
        "/api/employees",
        json={"first_name": "Menejer", "phone": "+998902222222", "role": "manager"},
        headers=auth(token),
    )
    manager_id = manager.json()["employee"]["id"]

    desk = await client.post(
        "/api/desks", json={"number": 1, "manager_id": manager_id}, headers=auth(token)
    )
    assert desk.status_code == 201
    assert desk.json()["manager_name"] == "Menejer"

    # scanner cannot be assigned as desk manager
    bad = await client.post(
        "/api/desks",
        json={"number": 2, "manager_id": scanner.json()["employee"]["id"]},
        headers=auth(token),
    )
    assert bad.status_code == 400

    # duplicate desk number
    dup = await client.post("/api/desks", json={"number": 1}, headers=auth(token))
    assert dup.status_code == 409
