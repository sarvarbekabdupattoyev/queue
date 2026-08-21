"""Sale-day burst hardening: the large code label on the ticket QR photo, the
millisecond registration time in the bot caption, the per-bot outbound rate
limiter with flood-control (429) handling, and the real health checks."""

from io import BytesIO

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import GetMe, SendMessage
from PIL import Image

from app.db.session import SessionFactory
from app.models import SaleEvent
from app.services import qr_service, queue_service, ticket_service
from app.services.telegram.throttle import (
    RETRY_ATTEMPTS,
    RateLimitMiddleware,
    SlidingWindowLimiter,
)
from tests.conftest import auth, create_company, event_times, register_owner


class FakeClock:
    """Injectable clock + sleep pair — tests never really sleep."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


# ------------------------------------------------------------ ticket photo ---

def test_ticket_qr_carries_large_code_label():
    plain = qr_service.qr_png_bytes("NVB-KJZR-AB12CD")
    labeled = qr_service.ticket_qr_png_bytes("NVB-KJZR-AB12CD", "№KJZR")
    plain_img = Image.open(BytesIO(plain))
    labeled_img = Image.open(BytesIO(labeled))
    # same QR width, plus a label band tall enough for large type below it
    assert labeled_img.width == plain_img.width
    assert labeled_img.height > plain_img.height + 20
    band = labeled_img.convert("L").crop(
        (0, plain_img.height, labeled_img.width, labeled_img.height)
    )
    assert min(band.getdata()) < 100  # the label is actually drawn, not blank


async def test_bot_ticket_caption_shows_ms_registration_time(client):
    token = (await register_owner(client))["access_token"]
    await create_company(client, token)
    event_resp = await client.post(
        "/api/events", json={"name": "Sotuv kuni", **event_times()}, headers=auth(token)
    )
    event_id = event_resp.json()["id"]

    class FakeMessage:
        def __init__(self) -> None:
            self.photos: list[tuple[object, str]] = []

        async def answer_photo(self, photo, caption, reply_markup=None) -> None:
            self.photos.append((photo, caption))

    from app.services.telegram.handlers import _deliver_ticket, _ticket_message

    async with SessionFactory() as db:
        event = await db.get(SaleEvent, event_id)
        ticket = await ticket_service.create_ticket(
            db, event, first_name="Sardor", last_name="Rahimov",
            phone="+998901112233", telegram_chat_id=808,
        )
        # the caption is built while the session is open...
        ticket_message = await _ticket_message(db, ticket, "uz")

    # ...and the photo goes out after it is closed, so a rate-limited upload
    # never keeps a pooled database connection to itself
    message = FakeMessage()
    await _deliver_ticket(message, ticket_message, "uz")
    assert len(message.photos) == 1
    caption = message.photos[0][1]
    assert f"№{ticket.number}" in caption
    # the exact bot registration moment, milliseconds included — it IS
    # the queue order the client will be served in
    assert queue_service.fmt_local_ms(ticket.registered_at) in caption


# ------------------------------------------------------------- rate limiter ---

async def test_limiter_paces_to_the_configured_rate():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(rate=25, per=1.0, clock=clock, sleeper=clock.sleep)
    for _ in range(25):
        await limiter.acquire()
    assert clock.now == 0.0  # a full window fits without waiting
    await limiter.acquire()  # 26th must wait for the window to roll over
    assert clock.now == pytest.approx(1.0)
    for _ in range(24):  # the rolled-over window has room for 24 more
        await limiter.acquire()
    assert clock.now == pytest.approx(1.0)


async def test_middleware_obeys_retry_after_then_retries():
    clock = FakeClock()
    middleware = RateLimitMiddleware(
        SlidingWindowLimiter(clock=clock, sleeper=clock.sleep), sleeper=clock.sleep
    )
    method = SendMessage(chat_id=1, text="salom")
    calls = 0

    async def make_request(bot, m):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TelegramRetryAfter(
                method=m, message="Too Many Requests: retry after 3", retry_after=3
            )
        return "sent"

    assert await middleware(make_request, None, method) == "sent"
    assert calls == 2
    assert clock.now == pytest.approx(4.0)  # slept retry_after (3s) + 1s margin


async def test_middleware_gives_up_after_bounded_attempts():
    clock = FakeClock()
    middleware = RateLimitMiddleware(
        SlidingWindowLimiter(clock=clock, sleeper=clock.sleep), sleeper=clock.sleep
    )
    method = SendMessage(chat_id=1, text="salom")
    calls = 0

    async def make_request(bot, m):
        nonlocal calls
        calls += 1
        raise TelegramRetryAfter(
            method=m, message="Too Many Requests: retry after 1", retry_after=1
        )

    with pytest.raises(TelegramRetryAfter):
        await middleware(make_request, None, method)
    assert calls == RETRY_ATTEMPTS


async def test_middleware_paces_send_methods_only():
    class CountingLimiter(SlidingWindowLimiter):
        acquired = 0

        async def acquire(self) -> None:
            type(self).acquired += 1

    limiter = CountingLimiter()
    middleware = RateLimitMiddleware(limiter)

    async def make_request(bot, m):
        return "ok"

    await middleware(make_request, None, GetMe())
    assert CountingLimiter.acquired == 0  # service calls are not throttled
    await middleware(make_request, None, SendMessage(chat_id=1, text="salom"))
    assert CountingLimiter.acquired == 1


# ------------------------------------------------------------------- health ---

async def test_health_endpoint_checks_the_database(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
