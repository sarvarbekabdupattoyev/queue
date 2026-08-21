import asyncio
import base64
import logging
import multiprocessing
import os
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.pil import PilImage

log = logging.getLogger(__name__)

# common DejaVu locations (Debian/Alpine images); Pillow's bundled scalable
# default font is the fallback, and the tiny bitmap font the last resort
_LABEL_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
)


def _qr_image(data: str, box_size: int) -> PilImage:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def qr_png_bytes(data: str, box_size: int = 12) -> bytes:
    buffer = BytesIO()
    _qr_image(data, box_size).save(buffer, format="PNG")
    return buffer.getvalue()


def _label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _LABEL_FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        # Pillow >= 10.1 ships a scalable built-in font
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow: tiny bitmap font only
        return ImageFont.load_default()


def ticket_qr_png_bytes(data: str, label: str, box_size: int = 12) -> bytes:
    """QR with the ticket code drawn LARGE underneath, so the code is readable
    at arm's length straight from the photo (clients show it at reception)."""
    qr_img = _qr_image(data, box_size).convert("RGB")
    width = qr_img.width
    font = _label_font(max(28, int(width * 0.24)))
    probe = ImageDraw.Draw(qr_img)
    left, top, right, bottom = probe.textbbox((0, 0), label, font=font)
    text_w, text_h = right - left, bottom - top
    band_h = text_h + max(18, width // 12)
    out = Image.new("RGB", (width, qr_img.height + band_h), "white")
    out.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.text(
        ((width - text_w) / 2 - left, qr_img.height + (band_h - text_h) / 2 - top),
        label,
        fill="black",
        font=font,
    )
    buffer = BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue()


def qr_data_url(data: str, box_size: int = 8) -> str:
    encoded = base64.b64encode(qr_png_bytes(data, box_size)).decode()
    return f"data:image/png;base64,{encoded}"


# QR rendering is ~2.5 ms of *pure Python* CPU (qrcode's matrix build holds
# the GIL), so threads don't parallelize it and 2000 registrations would
# serialize into ~5 s stolen from the event loop's process. A small
# ProcessPoolExecutor gives real parallelism; "spawn" avoids forking a
# process that already runs an event loop.

_pool: ProcessPoolExecutor | None = None

# Measured ~100-105 images/s with 4 workers (each render is ~40ms of pure
# Python CPU); 6 leaves 2 cores free for the event loop and other container
# work. Matches the bot service's CPU ceiling bump in docker-compose.prod.yml
# — raising one without the other does nothing, since Docker's cgroup CPU
# quota caps total usage regardless of worker count.
_QR_POOL_WORKERS = min(6, os.cpu_count() or 1)


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(
            max_workers=_QR_POOL_WORKERS,
            mp_context=multiprocessing.get_context("spawn"),
        )
    return _pool


def shutdown_qr_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def _discard_pool(pool: ProcessPoolExecutor) -> None:
    """Retire the pool that broke — and only that one.

    When a worker dies, every render in flight raises BrokenProcessPool. The
    first handler clears the pool and the next request builds a fresh one, so
    an unconditional shutdown from a slower handler would tear down that new,
    healthy pool and cancel the renders already queued on it.
    """
    global _pool
    if _pool is pool:
        _pool = None
    pool.shutdown(wait=False, cancel_futures=True)


async def _run_offloaded(func, *args):
    loop = asyncio.get_running_loop()
    pool = _get_pool()
    try:
        return await loop.run_in_executor(pool, func, *args)
    except BrokenProcessPool:
        log.warning("QR process pool broke; recreating and falling back to a thread")
        _discard_pool(pool)
        return await asyncio.to_thread(func, *args)


async def qr_png_bytes_async(data: str, box_size: int = 12) -> bytes:
    return await _run_offloaded(qr_png_bytes, data, box_size)


async def ticket_qr_png_bytes_async(data: str, label: str, box_size: int = 12) -> bytes:
    return await _run_offloaded(ticket_qr_png_bytes, data, label, box_size)


# A ticket's QR never changes, yet the public ticket page re-renders it on
# every poll (~40 ms of pool CPU and a fresh base64 blob each time). A small
# LRU keeps the tickets being looked at right now off the pool entirely.
_DATA_URL_CACHE_SIZE = 2048
_data_url_cache: OrderedDict[tuple[str, int], str] = OrderedDict()


async def qr_data_url_async(data: str, box_size: int = 8) -> str:
    key = (data, box_size)
    cached = _data_url_cache.get(key)
    if cached is not None:
        _data_url_cache.move_to_end(key)
        return cached
    encoded = await _run_offloaded(qr_data_url, data, box_size)
    _data_url_cache[key] = encoded
    _data_url_cache.move_to_end(key)
    while len(_data_url_cache) > _DATA_URL_CACHE_SIZE:
        _data_url_cache.popitem(last=False)
    return encoded
