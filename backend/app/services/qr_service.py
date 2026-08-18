import base64
from io import BytesIO

import qrcode
from qrcode.image.pil import PilImage


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
