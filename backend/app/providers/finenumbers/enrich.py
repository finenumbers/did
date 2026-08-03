"""Enrich catalog.operator from local PSTN INN cache + Finenumbers lookup.

Contour B: local cache is used ONLY to fill catalog.operator (no region/inventory).
RULE: every currently present catalog MSISDN must get a real non-empty operator.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.catalog import NumbersCatalogNormalized
from app.modules.pstn_inn_cache.service import load_enabled_ranges_for_enrich
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderError
from app.providers.finenumbers.client import FinenumbersClient
from app.providers.finenumbers.mapper import parse_msisdn_parts, phone_for_lookup

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, int | None, int | None], None]


@dataclass(frozen=True)
class OperatorRange:
    abc: str
    start: int
    end: int
    operator: str

    def covers(self, abc: str, local: int) -> bool:
        return self.abc == abc and self.start <= local <= self.end


class OperatorRangeCache:
    def __init__(self) -> None:
        self._by_abc: dict[str, list[OperatorRange]] = {}

    def add(self, abc: str, start: int, end: int, operator: str) -> None:
        if not abc or not operator or end < start:
            return
        bucket = self._by_abc.setdefault(abc, [])
        for existing in bucket:
            if existing.start == start and existing.end == end:
                return
        bucket.append(OperatorRange(abc=abc, start=start, end=end, operator=operator))

    def add_from_api_row(self, row: dict) -> str | None:
        abc = str(row.get("abc") or "").strip()
        operator = str(row.get("operator") or "").strip()
        try:
            start = int(row["rangeStart"])
            end = int(row["rangeEnd"])
        except (KeyError, TypeError, ValueError):
            return operator or None
        if operator:
            self.add(abc, start, end, operator)
        return operator or None

    def resolve(self, msisdn: str) -> str | None:
        parts = parse_msisdn_parts(msisdn)
        if not parts:
            return None
        abc, local = parts
        for r in self._by_abc.get(abc, []):
            if r.covers(abc, local):
                return r.operator
        return None


async def enrich_catalog_operators(
    db: Session,
    *,
    connection: ConnectionConfig,
    seed_ranges: list[dict] | None = None,
    batch_size: int = 1000,
    concurrency: int = 40,
    require_full_coverage: bool = True,
    max_rounds: int = 8,
    only_missing: bool = False,
    on_progress: ProgressCb | None = None,
) -> dict[str, int]:
    """
    Set operator on currently present catalog rows.

    Primary: local pstn_inn_ranges_cache (enabled INNs) — writes ONLY operator.
    Secondary: PSTN lookup API for remaining numbers.
    """
    client = FinenumbersClient(connection)
    cache = OperatorRangeCache()

    try:
        return await _enrich_catalog_operators_inner(
            db,
            client=client,
            cache=cache,
            seed_ranges=seed_ranges,
            batch_size=batch_size,
            concurrency=concurrency,
            require_full_coverage=require_full_coverage,
            max_rounds=max_rounds,
            only_missing=only_missing,
            on_progress=on_progress,
        )
    finally:
        await client.aclose()


def _progress(
    on_progress: ProgressCb | None,
    detail: str,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if on_progress is not None:
        try:
            on_progress(detail, current, total)
        except Exception:
            logger.exception("enrich progress callback failed")


async def _enrich_catalog_operators_inner(
    db: Session,
    *,
    client: FinenumbersClient,
    cache: OperatorRangeCache,
    seed_ranges: list[dict] | None,
    batch_size: int,
    concurrency: int,
    require_full_coverage: bool,
    max_rounds: int,
    only_missing: bool,
    on_progress: ProgressCb | None,
) -> dict[str, int]:
    _progress(on_progress, "Загрузка локального кеша операторов")
    local_ranges = load_enabled_ranges_for_enrich(db)
    for row in local_ranges:
        cache.add_from_api_row(row)
    logger.warning("PSTN enrich: seeded %s ranges from local INN cache", len(local_ranges))
    if seed_ranges:
        for row in seed_ranges:
            cache.add_from_api_row(row)

    stmt = select(
        NumbersCatalogNormalized.id,
        NumbersCatalogNormalized.msisdn,
        NumbersCatalogNormalized.operator,
    ).where(
        NumbersCatalogNormalized.is_currently_present.is_(True),
        NumbersCatalogNormalized.msisdn.is_not(None),
    )
    if only_missing:
        stmt = stmt.where(
            or_(
                NumbersCatalogNormalized.operator.is_(None),
                NumbersCatalogNormalized.operator == "",
            )
        )
    rows = db.execute(stmt).all()
    logger.warning("PSTN enrich: rows to process=%s only_missing=%s", len(rows), only_missing)
    _progress(on_progress, f"Сопоставление с кешем ({len(rows)} номеров)", 0, len(rows))

    pending_updates: list[tuple] = []
    cache_hits = 0
    lookups = 0
    errors = 0

    # (id, msisdn, phone, current_operator)
    pending: list[tuple] = []
    invalid_msisdns: list[str] = []

    for catalog_id, msisdn, current_operator in rows:
        msisdn_s = msisdn or ""
        operator = cache.resolve(msisdn_s)
        if operator:
            cache_hits += 1
            if current_operator != operator:
                pending_updates.append((catalog_id, operator))
            continue
        phone = phone_for_lookup(msisdn_s)
        if not phone:
            invalid_msisdns.append(msisdn_s)
            continue
        pending.append((catalog_id, msisdn_s, phone, current_operator))

    sem = asyncio.Semaphore(concurrency)
    # phone -> operator string, or None when API returned found=false / empty operator
    lookup_result: dict[str, str | None] = {}

    async def lookup_phone_row(phone: str) -> None:
        nonlocal lookups, errors
        async with sem:
            try:
                raw = await client.lookup_phone(phone)
                lookups += 1
                if raw.status_code >= 400:
                    errors += 1
                    # leave unset — retry in a later round
                    return
                body = raw.body_json if isinstance(raw.body_json, dict) else {}
                data = body.get("data") if body.get("found") else None
                if isinstance(data, dict):
                    op = cache.add_from_api_row(data)
                    lookup_result[phone] = op  # may be None if operator empty
                else:
                    lookup_result[phone] = None
            except Exception:
                errors += 1
                logger.exception("Finenumbers lookup failed for %s", phone)
                # leave unset so a later round can retry

    rounds = 0
    while pending and rounds < max_rounds:
        rounds += 1
        still: list[tuple] = []
        phones_needed: list[str] = []
        phone_seen: set[str] = set()

        for item in pending:
            catalog_id, msisdn_s, phone, current_operator = item
            operator = cache.resolve(msisdn_s)
            if not operator:
                op_direct = lookup_result.get(phone)
                if op_direct:
                    operator = op_direct
            if operator:
                cache_hits += 1
                if current_operator != operator:
                    pending_updates.append((catalog_id, operator))
                continue

            still.append(item)
            # Retry phones that never got a definitive API answer; skip confirmed None
            if phone not in phone_seen and phone not in lookup_result:
                phone_seen.add(phone)
                phones_needed.append(phone)

        pending = still
        if not phones_needed:
            break

        logger.warning(
            "PSTN enrich round=%s pending=%s phones_needed=%s lookups_so_far=%s",
            rounds,
            len(pending),
            len(phones_needed),
            lookups,
        )
        _progress(
            on_progress,
            f"PSTN lookup, волна {rounds}: {len(phones_needed)} запросов",
            lookups,
            lookups + len(phones_needed),
        )
        await asyncio.gather(*(lookup_phone_row(p) for p in phones_needed))

    # Final apply
    uncovered_msisdns: list[str] = list(invalid_msisdns)
    for item in pending:
        catalog_id, msisdn_s, phone, current_operator = item
        operator = cache.resolve(msisdn_s) or lookup_result.get(phone)
        if operator:
            cache_hits += 1
            if current_operator != operator:
                pending_updates.append((catalog_id, operator))
        else:
            uncovered_msisdns.append(msisdn_s)

    updated = 0
    for i in range(0, len(pending_updates), batch_size):
        chunk = pending_updates[i : i + batch_size]
        for catalog_id, operator in chunk:
            db.execute(
                update(NumbersCatalogNormalized)
                .where(NumbersCatalogNormalized.id == catalog_id)
                .values(operator=operator)
            )
            updated += 1
        db.commit()

    # Global coverage check (all present rows), not only this batch
    global_missing = int(
        db.scalar(
            select(func.count())
            .select_from(NumbersCatalogNormalized)
            .where(
                NumbersCatalogNormalized.is_currently_present.is_(True),
                NumbersCatalogNormalized.msisdn.is_not(None),
                or_(
                    NumbersCatalogNormalized.operator.is_(None),
                    NumbersCatalogNormalized.operator == "",
                ),
            )
        )
        or 0
    )

    stats = {
        "rows_scanned": len(rows),
        "updated": updated,
        "lookups": lookups,
        "cache_hits": cache_hits,
        "missing": max(len(uncovered_msisdns), global_missing),
        "invalid_msisdn": len(invalid_msisdns),
        "errors": errors,
        "waves": rounds,
        "global_missing": global_missing,
    }

    if require_full_coverage and (uncovered_msisdns or global_missing > 0):
        sample = uncovered_msisdns[:10]
        if not sample and global_missing:
            sample_rows = db.execute(
                select(NumbersCatalogNormalized.msisdn)
                .where(
                    NumbersCatalogNormalized.is_currently_present.is_(True),
                    or_(
                        NumbersCatalogNormalized.operator.is_(None),
                        NumbersCatalogNormalized.operator == "",
                    ),
                )
                .limit(10)
            ).scalars().all()
            sample = [str(x) for x in sample_rows]
        raise ProviderError(
            (
                f"PSTN coverage incomplete: {stats['missing']} numbers without "
                f"real PSTN operator (sample={sample})"
            ),
            code="PSTN_COVERAGE_INCOMPLETE",
            details={
                "uncovered": stats["missing"],
                "invalid_msisdn": len(invalid_msisdns),
                "sample_msisdn": sample,
                "stats": stats,
            },
        )

    return stats
