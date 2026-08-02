"""Split normalized Russian MSISDN into ABC code + local subscriber part."""

from __future__ import annotations


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
