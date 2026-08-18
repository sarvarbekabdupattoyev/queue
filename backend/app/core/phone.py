import re

_DIGITS = re.compile(r"\D")


def normalize_phone(raw: str | None) -> str | None:
    """Normalize an Uzbek phone number to +998XXXXXXXXX, or None if invalid."""
    digits = _DIGITS.sub("", raw or "")
    if len(digits) == 9:  # 90 123 45 67
        digits = "998" + digits
    if len(digits) == 10 and digits.startswith("8"):  # legacy 8-prefix
        digits = "99" + digits
    if len(digits) != 12 or not digits.startswith("998"):
        return None
    return "+" + digits


def pretty_phone(phone: str) -> str:
    m = re.fullmatch(r"\+998(\d{2})(\d{3})(\d{2})(\d{2})", phone or "")
    if not m:
        return phone
    return f"+998 {m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}"
