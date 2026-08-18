import asyncio
import base64
import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from io import BytesIO

import qrcode
from qrcode.image.pil import PilImage

log = logging.getLogger(__name__)


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


def qr_data_url(data: str, box_size: int = 8) -> str:
    encoded = base64.b64encode(qr_png_bytes(data, box_size)).decode()
    return f"data:image/png;base64,{encoded}"


# QR rendering is ~2.5 ms of *pure Python* CPU (qrcode's matrix build holds
# the GIL), so threads don't parallelize it and 2000 registrations would
# serialize into ~5 s stolen from the event loop's process. A small
# ProcessPoolExecutor gives real parallelism; "spawn" avoids forking a
# process that already runs an event loop.

_pool: ProcessPoolExecutor | None = None


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(
            max_workers=min(4, os.cpu_count() or 1),
            mp_context=multiprocessing.get_context("spawn"),
        )
    return _pool


def shutdown_qr_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


async def _run_offloaded(func, *args):
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(_get_pool(), func, *args)
    except BrokenProcessPool:
        log.warning("QR process pool broke; recreating and falling back to a thread")
        shutdown_qr_pool()
        return await asyncio.to_thread(func, *args)


async def qr_png_bytes_async(data: str, box_size: int = 12) -> bytes:
    return await _run_offloaded(qr_png_bytes, data, box_size)


async def qr_data_url_async(data: str, box_size: int = 8) -> str:
    return await _run_offloaded(qr_data_url, data, box_size)
