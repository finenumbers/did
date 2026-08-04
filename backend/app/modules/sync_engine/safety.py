"""Guards against destructive wipe-then-reload on empty/collapsed fetches."""

from __future__ import annotations

from typing import Iterable

from app.providers.dto.numbers import NormalizedNumber


def count_unique_provider_keys(numbers: Iterable[NormalizedNumber]) -> int:
    """Count distinct provider_number_key values (mirrors persist last-wins set size)."""
    keys = {n.provider_number_key for n in numbers if n.provider_number_key}
    return len(keys)


def reload_allowed(*, previous: int, incoming: int, kind: str) -> tuple[bool, str | None]:
    """
    Decide whether wipe+reload is safe.

    - Empty incoming never wipes existing rows.
    - Free (large): require >= ~90% of previous (incomplete provider fetches).
    - Purchased / small sets (<100): refuse drops worse than half.
    - previous==0 allows first load / recovery of any positive fetch.

    `incoming` must be the post-dedupe unique key count that will actually be written.
    """
    if incoming <= 0:
        if previous <= 0:
            return False, f"Empty {kind} fetch; nothing to load"
        return (
            False,
            f"Refusing wipe: empty {kind} fetch while catalog has {previous} rows",
        )
    if previous <= 0:
        return True, None
    if kind == "free" or previous >= 100:
        # Large / free catalogs: reject incomplete-but-large fetches
        min_allowed = max(50, int(previous * 0.9))
    else:
        # Small purchased sets: refuse drops worse than half
        min_allowed = max(1, previous // 2)
    if incoming < min_allowed:
        return (
            False,
            (
                f"Refusing wipe: {kind} fetch={incoming} << previous={previous} "
                f"(min_allowed={min_allowed})"
            ),
        )
    return True, None
