import os
import tempfile
from pathlib import Path

# Configure the app BEFORE anything under `app` is imported: tests run with
# Telegram disabled and an isolated throw-away SQLite database.
_TMP = Path(tempfile.mkdtemp(prefix="navbat-test-"))
os.environ["TELEGRAM_ENABLED"] = "0"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["SECRET_KEY"] = "test-secret"

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.session import engine
from app.main import app


@pytest.fixture(autouse=True)
async def _fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def register_owner(client: AsyncClient, phone: str = "+998901234567") -> dict:
    response = await client.post(
        "/api/auth/register",
        json={
            "first_name": "Sarvar",
            "last_name": "Abdupattoyev",
            "phone": phone,
            "password": "secret123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def create_company(client: AsyncClient, token: str, name: str = "Bahor City") -> dict:
    response = await client.post("/api/company", json={"name": name}, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()
