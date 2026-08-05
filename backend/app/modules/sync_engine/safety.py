"""Guards against destructive wipe-then-reload on empty fetches."""

from __future__ import annotations

from typing import Any, Iterable

from app.providers.dto.numbers import NormalizedNumber

_PROVIDER_LABELS: dict[str, str] = {
    "sipout": "SipOut",
    "runexis": "Runexis",
    "uis": "UIS",
    "aurora": "Aurora Telecom",
    "finenumbers": "Finenumbers",
}
_KIND_LABELS: dict[str, str] = {
    "free_numbers": "свободные",
    "purchased_numbers": "купленные",
}
_KIND_SHORT: dict[str, str] = {
    "free_numbers": "free",
    "purchased_numbers": "purchased",
}


def count_unique_provider_keys(numbers: Iterable[NormalizedNumber]) -> int:
    """Count distinct provider_number_key values (mirrors persist last-wins set size)."""
    keys = {n.provider_number_key for n in numbers if n.provider_number_key}
    return len(keys)


def reload_allowed(*, previous: int, incoming: int, kind: str) -> tuple[bool, str | None]:
    """
    Decide whether wipe+reload is safe.

    Full replace is always allowed when ``incoming > 0`` (count may shrink or grow).
    Empty incoming never wipes existing rows; empty-on-empty is also refused.
    Size-ratio thresholds are intentionally not used.
    """
    if incoming <= 0:
        if previous <= 0:
            return False, f"Empty {kind} fetch; nothing to load"
        return (
            False,
            f"Refusing wipe: empty {kind} fetch while catalog has {previous} rows",
        )
    return True, None


def build_inventory_summary(category_stats: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten per-provider free/purchased reload stats into was/became rows."""
    rows: list[dict[str, Any]] = []
    for provider, cats in (category_stats or {}).items():
        if provider == "operator_enrichment" or not isinstance(cats, dict):
            continue
        label_provider = _PROVIDER_LABELS.get(provider, provider)
        for cat_key, kind_short in _KIND_SHORT.items():
            block = cats.get(cat_key)
            if not isinstance(block, dict):
                continue
            if block.get("limited") or block.get("refused_wipe"):
                # Still show refused/limited with previous/incoming when present
                previous = int(block.get("previous") or 0)
                current = int(block.get("incoming") or block.get("upserted") or 0)
                if previous == 0 and current == 0 and not block.get("refused_wipe"):
                    continue
            else:
                if "previous" not in block and "upserted" not in block:
                    continue
                previous = int(block.get("previous") or 0)
                current = int(block.get("upserted") or 0)
            kind_label = _KIND_LABELS.get(cat_key, kind_short)
            rows.append(
                {
                    "provider": provider,
                    "kind": kind_short,
                    "label": f"{label_provider} · {kind_label}",
                    "previous": previous,
                    "current": current,
                    "delta": current - previous,
                    "refused_wipe": bool(block.get("refused_wipe")),
                    "limited": bool(block.get("limited")),
                }
            )
    return rows
