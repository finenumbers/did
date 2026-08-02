"""Guards against destructive wipe-then-reload on empty/collapsed fetches."""

from __future__ import annotations


def reload_allowed(*, previous: int, incoming: int, kind: str) -> tuple[bool, str | None]:
    """
    Decide whether wipe+reload is safe.

    - Empty incoming never wipes existing rows.
    - Free (large): require >= ~90% of previous (incomplete provider fetches).
    - Purchased / small sets (<100): refuse drops worse than half.
    - previous==0 allows first load / recovery of any positive fetch.
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


def fetch_complete_enough(*, expected: int, fetched: int) -> tuple[bool, str | None]:
    """Provider count vs list completeness (Runexis Numbering)."""
    if expected <= 0:
        return True, None
    if fetched <= 0:
        return False, f"Empty fetch while provider count={expected}"
    # Allow tiny rounding gaps; refuse if below 95% or gap > 1000 on large sets
    min_ok = int(expected * 0.95)
    if expected >= 1000:
        min_ok = max(min_ok, expected - 1000)
    if fetched < min_ok:
        return (
            False,
            f"Incomplete fetch: got {fetched} while count={expected} (min_ok={min_ok})",
        )
    return True, None
