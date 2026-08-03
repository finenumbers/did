"""ABC-based number category (line kind) for catalog UI."""

from __future__ import annotations

CATEGORY_MOBILE = "Мобильный"
CATEGORY_TOLLFREE = "Бесплатный вызов"
CATEGORY_GEOGRAPHIC = "Городской"


def resolve_abc_code(abc_code: str | None, msisdn: str | None = None) -> str | None:
    abc = (abc_code or "").strip()
    if abc:
        return abc
    ms = (msisdn or "").strip()
    if len(ms) >= 4 and ms.startswith("7") and ms[1:4].isdigit():
        return ms[1:4]
    return None


def classify_number_category(
    abc_code: str | None, msisdn: str | None = None
) -> str | None:
    """
    Classify by ABC:
    - starts with 9 → Мобильный
    - exactly 800 → Бесплатный вызов
    - otherwise (present) → Городской
    """
    abc = resolve_abc_code(abc_code, msisdn)
    if not abc:
        return None
    if abc.startswith("9"):
        return CATEGORY_MOBILE
    if abc == "800":
        return CATEGORY_TOLLFREE
    return CATEGORY_GEOGRAPHIC
