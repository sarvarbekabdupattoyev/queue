"""Burst-load machinery: debounced broadcasts, notify routing, webhook auth,
and the Redis pub/sub fan-out (against a real redis-server)."""

import asyncio
import json
import socket
import subprocess
from types import SimpleNamespace

import pytest
from redis.asyncio import Redis

import app.core.redis as redis_core
from app.services import broadcast, notify
from app.services.telegram.manager import bot_manager, webhook_secret
from app.ws.manager import ws_manager
from tests.conftest import auth, create_company, register_owner
from tests.test_queue_logic import create_event


async def _wait_for(predicate, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


# ------------------------------------------------------------- debouncing ---

async def test_broadcast_burst_coalesces_into_one_rebuild(client, monkeypatch):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    event = await create_event(client, token)

    published: list[str] = []

    async def fake_publish(room: str, payload: dict) -> None:
        published.append(room)

    monkeypatch.setattr(ws_manager, "publish", fake_publish)

    # a registration burst marks the event dirty hundreds of times...
    for _ in range(300):
        broadcast.schedule_event_broadcast(event["id"])
    await asyncio.sleep(0.25)

    # ...but the state is rebuilt and pushed exactly once (display + staff)
    assert sorted(published) == [f"display:{event['id']}", f"staff:{event['id']}"]

    # a second wave after the window produces exactly one more pair
    broadcast.schedule_event_broadcast(event["id"])
    await asyncio.sleep(0.25)
    assert len(published) == 4


async def test_broadcast_for_missing_event_is_silent(monkeypatch):
    published = []

    async def fake_publish(room, payload):
        published.append(room)

    monkeypatch.setattr(ws_manager, "publish", fake_publish)
    broadcast.schedule_event_broadcast(999_999)
    await asyncio.sleep(0.15)
    assert published == []


# ----------------------------------------------------------- notify paths ---

async def test_notify_embedded_mode_hands_to_bot_manager(monkeypatch):
    sent = []

    async def fake_send(company_id, chat_id, text):
        sent.append((company_id, chat_id, text))

    monkeypatch.setattr(bot_manager, "send_text", fake_send)
    await notify.send_telegram_text(7, 1234, "salom")
    await _wait_for(lambda: sent == [(7, 1234, "salom")])


# ------------------------------------------------------------ webhook auth ---

async def test_webhook_secret_is_deterministic_and_scoped():
    assert webhook_secret(1) == webhook_secret(1)
    assert webhook_secret(1) != webhook_secret(2)
    assert 1 <= len(webhook_secret(1)) <= 256


async def test_feed_webhook_validates_secret_and_bounds_processing():
    processed = []

    async def fake_feed(payload):
        processed.append(payload)

    runner = SimpleNamespace(feed_update=fake_feed, bot=None)
    bot_manager._runners[42] = runner
    try:
        # wrong secret → rejected, unknown company → rejected
        assert await bot_manager.feed_webhook(42, "wrong", {"update_id": 1}) is False
        assert await bot_manager.feed_webhook(43, webhook_secret(43), {"update_id": 1}) is False
        # correct secret → accepted and processed in the background
        assert await bot_manager.feed_webhook(42, webhook_secret(42), {"update_id": 7}) is True
        await _wait_for(lambda: processed == [{"update_id": 7}])
    finally:
        bot_manager._runners.pop(42, None)


# ------------------------------------------------- redis pub/sub (real server) ---

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
async def redis_client():
    port = _free_port()
    proc = subprocess.Popen(
        ["redis-server", "--port", str(port), "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = Redis.from_url(f"redis://127.0.0.1:{port}/0", decode_responses=True)
    try:
        for _ in range(100):
            try:
                if await client.ping():
                    break
            except Exception:
                await asyncio.sleep(0.05)
        else:
            raise RuntimeError("redis-server did not come up")
        yield client
    finally:
        await client.aclose()
        proc.terminate()
        proc.wait(timeout=5)


async def test_ws_fanout_via_redis(redis_client, monkeypatch):
    """publish() on one worker reaches deliver_local() on every subscriber."""
    monkeypatch.setattr(redis_core, "_client", redis_client)
    delivered: list[tuple[str, str]] = []

    async def fake_deliver(room: str, message: str) -> None:
        delivered.append((room, message))

    monkeypatch.setattr(ws_manager, "deliver_local", fake_deliver)
    subscriber = asyncio.create_task(ws_manager.run_subscriber())
    try:
        await asyncio.sleep(0.2)  # let SUBSCRIBE land
        await ws_manager.publish("display:5", {"stats": {"waiting": 3}})
        await _wait_for(lambda: len(delivered) == 1)
        room, message = delivered[0]
        assert room == "display:5"
        assert json.loads(message)["stats"]["waiting"] == 3
    finally:
        subscriber.cancel()
        with pytest.raises(asyncio.CancelledError):
            await subscriber


async def test_notify_roundtrip_via_redis(redis_client, monkeypatch):
    """API worker publishes; the bot service consumes and sends to the chat."""
    monkeypatch.setattr(redis_core, "_client", redis_client)
    sent = []

    async def fake_send(company_id, chat_id, text):
        sent.append((company_id, chat_id, text))

    monkeypatch.setattr(bot_manager, "send_text", fake_send)
    subscriber = asyncio.create_task(bot_manager.run_notify_subscriber())
    try:
        await asyncio.sleep(0.2)
        await notify.send_telegram_text(9, 555, "Navbatingiz keldi")
        await _wait_for(lambda: sent == [(9, 555, "Navbatingiz keldi")])
    finally:
        subscriber.cancel()
        with pytest.raises(asyncio.CancelledError):
            await subscriber


async def test_bot_control_roundtrip_via_redis(redis_client, monkeypatch):
    monkeypatch.setattr(redis_core, "_client", redis_client)
    reloaded = []

    async def fake_reload(company_id):
        reloaded.append(company_id)

    monkeypatch.setattr(bot_manager, "reload_company", fake_reload)
    subscriber = asyncio.create_task(bot_manager.run_control_subscriber())
    try:
        await asyncio.sleep(0.2)
        await notify.notify_bot_token_changed(31)
        await _wait_for(lambda: reloaded == [31])
    finally:
        subscriber.cancel()
        with pytest.raises(asyncio.CancelledError):
            await subscriber
