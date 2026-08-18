"""Normalize and split Russian MSISDN helpers shared across providers."""

from __future__ import annotations

from typing import Any


def normalize_phone(value: Any) -> str | None:
    """Normalize RU MSISDN to 7XXXXXXXXXX; otherwise None."""
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits.startswith("7"):
        return digits
    return None



DIGIT_CAPACITY_DEFAULT = 7
DIGIT_CAPACITY_MIN = 5
DIGIT_CAPACITY_MAX = 7


def split_msisdn(msisdn: str | None) -> tuple[str | None, str | None]:
    """Return (abc_code, number_local) for 7XXXXXXXXXX; otherwise (None, None)."""
    parts = split_msisdn_by_capacity(msisdn, DIGIT_CAPACITY_DEFAULT)
    if parts is None:
        return None, None
    return parts


def split_msisdn_by_capacity(
    msisdn: str | None, capacity: int
) -> tuple[str, str] | None:
    """Strip leading 7, then split remaining 10 digits by local-part length."""
    if capacity < DIGIT_CAPACITY_MIN or capacity > DIGIT_CAPACITY_MAX:
        return None
    if not msisdn:
        return None
    digits = "".join(ch for ch in str(msisdn).strip() if ch.isdigit())
    if len(digits) != 11 or not digits.startswith("7"):
        return None
    national = digits[1:]
    abc_len = 10 - capacity
    if abc_len < 1:
        return None
    abc = national[:abc_len]
    local = national[abc_len:]
    if not abc or not local:
        return None
    return abc, local


def split_from_parts(
    *,
    msisdn: str | None,
    code: str | None = None,
    number: str | None = None,
) -> tuple[str | None, str | None]:
    """Prefer split from full msisdn; fall back to provider code + local number."""
    abc, local = split_msisdn(msisdn)
    if abc and local:
        return abc, local
    code_s = str(code).strip() if code else ""
    number_s = str(number).strip() if number else ""
    if code_s.isdigit() and number_s.isdigit():
        return code_s, number_s
    return None, None
