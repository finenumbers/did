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



def split_msisdn(msisdn: str | None) -> tuple[str | None, str | None]:
    """Return (abc_code, number_local) for 7XXXXXXXXXX; otherwise (None, None)."""
    if not msisdn:
        return None, None
    digits = "".join(ch for ch in str(msisdn).strip() if ch.isdigit())
    if len(digits) == 11 and digits.startswith("7"):
        return digits[1:4], digits[4:]
    return None, None


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
