import os
import tempfile
from pathlib import Path

# Configure the app BEFORE anything under `app` is imported: tests run with
# Telegram disabled and an isolated throw-away SQLite database.
_TMP = Path(tempfile.mkdtemp(prefix="navbat-test-"))
os.environ["TELEGRAM_ENABLED"] = "0"
# Default: throw-away SQLite. Set TEST_DATABASE_URL to run the same suite
# against PostgreSQL (e.g. postgresql+asyncpg://navbat@127.0.0.1:5544/navbat).
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite+aiosqlite:///{_TMP / 'test.db'}"
)
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["BROADCAST_DEBOUNCE_MS"] = "50"

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.base import Base, now_utc
from app.db.session import engine
from app.main import app
from app.services import broadcast


@pytest.fixture(autouse=True)
async def _fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    # cancel debounced broadcast tasks so they never leak into the next
    # test's database (event ids repeat across fresh databases)
    await broadcast.shutdown()
    # pytest-asyncio gives every test its own event loop, but the global
    # engine pool would happily hand a connection created on the previous
    # loop to the next test — fatal with asyncpg. Drop pooled connections
    # while their loop is still alive.
    await engine.dispose()


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


def event_times(
    *, reg_min: int = 30, starts_min: int = 30, checkin_min: int = 60, sale_min: int = 90
) -> dict:
    """The three periods of an event, as minute offsets from now: on-time
    registration ends, QR scanning runs, the sale starts. Defaults keep
    registration AND scanning open right now, sale not yet started."""
    now = now_utc()
    return {
        "registration_until": (now + timedelta(minutes=reg_min)).isoformat(),
        "starts_at": (now + timedelta(minutes=starts_min)).isoformat(),
        "checkin_until": (now + timedelta(minutes=checkin_min)).isoformat(),
        "sale_starts_at": (now + timedelta(minutes=sale_min)).isoformat(),
    }


def started_sale_times() -> dict:
    """Every period in the past: scanning window over, sale running."""
    now = now_utc()
    return {
        "registration_until": (now - timedelta(hours=3)).isoformat(),
        "starts_at": (now - timedelta(hours=3)).isoformat(),
        "checkin_until": (now - timedelta(minutes=2)).isoformat(),
        "sale_starts_at": (now - timedelta(minutes=1)).isoformat(),
    }
