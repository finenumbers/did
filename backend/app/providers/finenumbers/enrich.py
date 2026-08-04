"""Enrich catalog.operator from local PSTN INN cache + Finenumbers lookup.

Contour B: local cache is used ONLY to fill catalog.operator (no region/inventory).
RULE: every currently present catalog MSISDN must get a real non-empty operator.
"""

from __future__ import annotations

import asyncio
import logging
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import bindparam, func, or_, select, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Session
from sqlalchemy.types import Text

from app.models.catalog import NumbersCatalogNormalized
from app.modules.pstn_inn_cache.service import load_enabled_ranges_for_enrich
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderError
from app.providers.finenumbers.client import FinenumbersClient
from app.providers.finenumbers.mapper import parse_msisdn_parts, phone_for_lookup

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, int | None, int | None], None]
_PROGRESS_EVERY = 50_000


@dataclass(frozen=True)
class OperatorRange:
    abc: str
    start: int
    end: int
    operator: str
    order: int = 0

    def covers(self, abc: str, local: int) -> bool:
        return self.abc == abc and self.start <= local <= self.end


class OperatorRangeCache:
    """ABC-bucketed ranges; resolve uses bisect + first-insert-order among covering."""

    def __init__(self) -> None:
        self._by_abc: dict[str, list[OperatorRange]] = {}
        self._starts: dict[str, list[int]] = {}
        self._order = 0
        self._finalized = False

    def add(self, abc: str, start: int, end: int, operator: str) -> None:
        if not abc or not operator or end < start:
            return
        self._finalized = False
        bucket = self._by_abc.setdefault(abc, [])
        for existing in bucket:
            if existing.start == start and existing.end == end:
                return
        self._order += 1
        bucket.append(
            OperatorRange(abc=abc, start=start, end=end, operator=operator, order=self._order)
        )

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

    def finalize(self) -> None:
        self._starts = {}
        for abc, bucket in self._by_abc.items():
            bucket.sort(key=lambda r: (r.start, r.end, r.order))
            self._starts[abc] = [r.start for r in bucket]
        self._finalized = True

    def resolve_parts(self, abc: str, local: int) -> str | None:
        if not self._finalized:
            self.finalize()
        bucket = self._by_abc.get(abc) or []
        if not bucket:
            return None
        starts = self._starts.get(abc) or []
        i = bisect_right(starts, local) - 1
        best_op: str | None = None
        best_order: int | None = None
        while i >= 0:
            r = bucket[i]
            if r.start <= local <= r.end:
                if best_order is None or r.order < best_order:
                    best_op = r.operator
                    best_order = r.order
            i -= 1
        return best_op

    def resolve(self, msisdn: str) -> str | None:
        parts = parse_msisdn_parts(msisdn)
        if not parts:
            return None
        abc, local = parts
        return self.resolve_parts(abc, local)

    def resolve_linear_first_match(self, msisdn: str) -> str | None:
        """Reference semantics (insertion order) for tests."""
        parts = parse_msisdn_parts(msisdn)
        if not parts:
            return None
        abc, local = parts
        for r in sorted(self._by_abc.get(abc) or [], key=lambda x: x.order):
            if r.covers(abc, local):
                return r.operator
        return None


async def enrich_catalog_operators(
    db: Session,
    *,
    connection: ConnectionConfig,
    seed_ranges: list[dict] | None = None,
    batch_size: int = 10_000,
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


def _bulk_update_operators(
    db: Session,
    pairs: list[tuple],
) -> int:
    """UPDATE operator for (id, operator) pairs via unnest; returns row count attempted."""
    if not pairs:
        return 0
    ids = [p[0] for p in pairs]
    ops = [p[1] for p in pairs]
    stmt = text(
        """
        UPDATE numbers_catalog_normalized AS c
        SET operator = v.operator
        FROM unnest(:ids, :ops) AS v(id, operator)
        WHERE c.id = v.id
        """
    ).bindparams(
        bindparam("ids", type_=ARRAY(PGUUID(as_uuid=True))),
        bindparam("ops", type_=ARRAY(Text())),
    )
    db.execute(stmt, {"ids": ids, "ops": ops})
    return len(pairs)


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
    cache.finalize()

    stmt = select(
        NumbersCatalogNormalized.id,
        NumbersCatalogNormalized.msisdn,
        NumbersCatalogNormalized.operator,
        NumbersCatalogNormalized.abc_code,
        NumbersCatalogNormalized.number_local,
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
    total_rows = len(rows)
    logger.warning("PSTN enrich: rows to process=%s only_missing=%s", total_rows, only_missing)
    _progress(on_progress, f"Сопоставление с кешем ({total_rows} номеров)", 0, total_rows)

    pending_updates: list[tuple] = []
    cache_hits = 0
    lookups = 0
    errors = 0

    # (id, msisdn, phone, current_operator)
    pending: list[tuple] = []
    invalid_msisdns: list[str] = []

    for idx, (catalog_id, msisdn, current_operator, abc_code, number_local) in enumerate(rows):
        msisdn_s = msisdn or ""
        operator: str | None = None
        if abc_code and number_local is not None:
            try:
                operator = cache.resolve_parts(str(abc_code).strip(), int(number_local))
            except (TypeError, ValueError):
                operator = None
        if operator is None:
            operator = cache.resolve(msisdn_s)
        if operator:
            cache_hits += 1
            if current_operator != operator:
                pending_updates.append((catalog_id, operator))
        else:
            phone = phone_for_lookup(msisdn_s)
            if not phone:
                invalid_msisdns.append(msisdn_s)
            else:
                pending.append((catalog_id, msisdn_s, phone, current_operator))
        if (idx + 1) % _PROGRESS_EVERY == 0:
            _progress(
                on_progress,
                f"Сопоставление с кешем ({idx + 1}/{total_rows})",
                idx + 1,
                total_rows,
            )

    if total_rows:
        _progress(
            on_progress,
            f"Сопоставление с кешем ({total_rows}/{total_rows})",
            total_rows,
            total_rows,
        )

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
                    return
                body = raw.body_json if isinstance(raw.body_json, dict) else {}
                data = body.get("data") if body.get("found") else None
                if isinstance(data, dict):
                    op = cache.add_from_api_row(data)
                    cache.finalize()
                    lookup_result[phone] = op
                else:
                    lookup_result[phone] = None
            except Exception:
                errors += 1
                logger.exception("Finenumbers lookup failed for %s", phone)

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
    write_total = len(pending_updates)
    _progress(on_progress, f"Запись операторов ({write_total})", 0, write_total or None)
    for i in range(0, len(pending_updates), batch_size):
        chunk = pending_updates[i : i + batch_size]
        try:
            updated += _bulk_update_operators(db, chunk)
        except Exception:
            logger.exception("Bulk operator update failed; falling back to row updates")
            for catalog_id, operator in chunk:
                db.execute(
                    text(
                        "UPDATE numbers_catalog_normalized "
                        "SET operator = :op WHERE id = :id"
                    ),
                    {"op": operator, "id": catalog_id},
                )
                updated += 1
        db.commit()
        if write_total and (i + len(chunk)) % _PROGRESS_EVERY < batch_size:
            _progress(
                on_progress,
                f"Запись операторов ({min(i + len(chunk), write_total)}/{write_total})",
                min(i + len(chunk), write_total),
                write_total,
            )
    if write_total:
        _progress(
            on_progress,
            f"Запись операторов ({write_total}/{write_total})",
            write_total,
            write_total,
        )

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
        "rows_scanned": total_rows,
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
                    NumbersCatalogNormalized.msisdn.is_not(None),
                    or_(
                        NumbersCatalogNormalized.operator.is_(None),
                        NumbersCatalogNormalized.operator == "",
                    ),
                )
                .limit(10)
            ).all()
            sample = [r[0] for r in sample_rows]
        raise ProviderError(
            (
                f"Operator enrichment incomplete: missing={stats['missing']} "
                f"invalid_msisdn={stats['invalid_msisdn']} errors={errors} "
                f"sample={sample}"
            ),
            code="OPERATOR_ENRICHMENT_INCOMPLETE",
            details=stats,
        )

    return stats
