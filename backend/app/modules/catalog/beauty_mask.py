"""Beauty masks from local number digits (not provider API masks)."""

from __future__ import annotations

from functools import lru_cache

LETTERS = "XYZABCDEF"
_VALID_LENGTHS = frozenset({5, 6, 7})


def digits_only(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def beauty_mask(number_local: str | None) -> str | None:
    """Map a local number to a canonical mask, or None if length is not 5/6/7."""
    digits = digits_only(number_local)
    if len(digits) not in _VALID_LENGTHS:
        return None
    letter_for: dict[str, str] = {}
    next_i = 0
    out: list[str] = []
    for ch in digits:
        if ch == "0":
            out.append("0")
            continue
        mapped = letter_for.get(ch)
        if mapped is None:
            mapped = LETTERS[next_i]
            letter_for[ch] = mapped
            next_i += 1
        out.append(mapped)
    return "".join(out)


def enumerate_beauty_masks(length: int) -> tuple[str, ...]:
    """All restricted-growth masks of the given length (0 is a free literal)."""
    if length not in _VALID_LENGTHS:
        raise ValueError(f"unsupported mask length: {length}")
    return _enumerate_cached(length)


@lru_cache(maxsize=4)
def _enumerate_cached(length: int) -> tuple[str, ...]:
    out: list[str] = []

    def rec(pos: int, used: int, current: list[str]) -> None:
        if pos == length:
            out.append("".join(current))
            return
        current.append("0")
        rec(pos + 1, used, current)
        current.pop()
        for i in range(used):
            current.append(LETTERS[i])
            rec(pos + 1, used, current)
            current.pop()
        if used < len(LETTERS):
            current.append(LETTERS[used])
            rec(pos + 1, used + 1, current)
            current.pop()

    rec(0, 0, [])
    return tuple(out)


def all_beauty_masks() -> tuple[str, ...]:
    return enumerate_beauty_masks(5) + enumerate_beauty_masks(6) + enumerate_beauty_masks(7)


@lru_cache(maxsize=1)
def canonical_beauty_masks() -> frozenset[str]:
    return frozenset(all_beauty_masks())


def mask_digit_capacity(mask: str) -> str:
    """Разрядность канонической маски — её длина (5/6/7)."""
    return str(len(mask))
