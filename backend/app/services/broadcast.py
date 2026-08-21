"""Debounced event-state broadcasts.

During a registration burst (1000–2000 bot requests in a few seconds) every
mutation used to rebuild the full event state and push it to every screen.
This module coalesces that: callers mark an event dirty with
:func:`schedule_event_broadcast` (cheap, synchronous, fire-and-forget) and a
single task per event rebuilds the state at most once per debounce window,
in its own DB session, off the request path.
"""

import asyncio
import logging

from app.core.config import get_settings

log = logging.getLogger(__name__)

_tasks: dict[int, asyncio.Task] = {}
_dirty: set[int] = set()
_shutting_down = False

# A rebuild that keeps failing (database down) must not spin on the debounce
# interval forever; after this many consecutive failures the event is dropped
# and the next mutation starts a fresh task.
_MAX_CONSECUTIVE_FAILURES = 5


def schedule_event_broadcast(event_id: int) -> None:
    """Mark an event's state as changed. Safe to call thousands of times per
    second — bursts collapse into one rebuild per debounce window."""
    if _shutting_down:
        return
    if event_id in _tasks:
        _dirty.add(event_id)
        return
    _tasks[event_id] = asyncio.get_running_loop().create_task(
        _flush_loop(event_id), name=f"broadcast-{event_id}"
    )


async def _flush_loop(event_id: int) -> None:
    failures = 0
    try:
        while True:
            await asyncio.sleep(get_settings().broadcast_debounce_ms / 1000)
            _dirty.discard(event_id)
            try:
                await _build_and_publish(event_id)
            except Exception:
                # The change that woke us is still unpublished. Leaving it
                # dropped would freeze every screen on a stale queue until the
                # next mutation happens to succeed, so keep the event dirty and
                # retry in the next window.
                failures += 1
                log.exception(
                    "State broadcast for event %s failed (attempt %s/%s)",
                    event_id,
                    failures,
                    _MAX_CONSECUTIVE_FAILURES,
                )
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    return
                _dirty.add(event_id)
            else:
                failures = 0
            if event_id not in _dirty:
                return
    except asyncio.CancelledError:
        raise
    finally:
        _tasks.pop(event_id, None)
        # a schedule() call that raced with our exit gets a fresh task — but
        # never during shutdown, where it would outlive the cancelled set
        if event_id in _dirty and not _shutting_down:
            _dirty.discard(event_id)
            schedule_event_broadcast(event_id)


async def _build_and_publish(event_id: int) -> None:
    from app.db.session import SessionFactory
    from app.models import SaleEvent
    from app.services import queue_service
    from app.ws.manager import ws_manager

    async with SessionFactory() as db:
        event = await db.get(SaleEvent, event_id)
        if event is None:
            return
        public_state, staff_state = await queue_service.build_states(db, event)
    await ws_manager.publish(f"display:{event_id}", public_state)
    await ws_manager.publish(f"staff:{event_id}", staff_state)


async def flush_now(event_id: int) -> None:
    """Immediate rebuild+publish, bypassing the debounce (tests, shutdown)."""
    await _build_and_publish(event_id)


async def shutdown() -> None:
    global _shutting_down
    _shutting_down = True
    try:
        for task in list(_tasks.values()):
            task.cancel()
        for task in list(_tasks.values()):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        _tasks.clear()
        _dirty.clear()
    finally:
        # the flag only guards this teardown; the process (or the next test)
        # must be able to broadcast again afterwards
        _shutting_down = False
