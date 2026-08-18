"""Enrich catalog operator and GAR city/region from local PSTN INN cache + lookup.

Contour B: every currently present catalog MSISDN goes through cache → PSTN lookup
when needed. Operator SoT is this last sync stage (or «Нет в реестре» on terminal miss).
When garTerritory is present, overlay city_name/region_name from the parsed GAR value.
Terminal PSTN miss writes «Нет в реестре» on operator, city_name, and region_name.
"""

from __future__ import annotations

import asyncio
import logging
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import Boolean, bindparam, func, or_, select, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Session
from sqlalchemy.types import Text

from app.models.catalog import NumbersCatalogNormalized
from app.modules.catalog.gar_territory import parse_gar_territory
from app.modules.pstn_inn_cache.service import load_enabled_ranges_for_enrich
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderError
from app.providers.finenumbers import contract
from app.providers.finenumbers.client import FinenumbersClient
from app.providers.finenumbers.mapper import parse_msisdn_parts, phone_for_lookup

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, int | None, int | None], None]
_PROGRESS_EVERY = 50_000
_WAVE_PROGRESS_EVERY = 200

# Client 4xx that mean "phone absent / invalid", not auth or transport failure.
_ABSENT_HTTP_STATUSES = frozenset({400, 404, 422})


class LookupClass(str, Enum):
    found = "found"
    absent = "absent"
    error = "error"


def classify_lookup_response(raw: RawHttpResult) -> LookupClass:
    """
    Classify PSTN lookup outcome for operator SoT.

    absent — confirmed not in registry (write «Нет в реестре»).
    error — transport/auth/5xx (do not write sentinel; may retry).
    found — HTTP 200 with found+data (caller extracts operator via cache).
    """
    status = int(raw.status_code or 0)
    if status in _ABSENT_HTTP_STATUSES:
        return LookupClass.absent
    if status >= 400:
        # 401/403/other 4xx and 5xx: not a confirmed registry miss
        return LookupClass.error
    body = raw.body_json if isinstance(raw.body_json, dict) else {}
    data = body.get("data") if body.get("found") else None
    if isinstance(data, dict) and str(data.get("operator") or "").strip():
        return LookupClass.found
    return LookupClass.absent


def _body_snippet(raw: RawHttpResult, limit: int = 200) -> str:
    text_body = (raw.body_text or "").strip()
    if text_body:
        return text_body[:limit]
    if isinstance(raw.body_json, dict):
        return str(raw.body_json)[:limit]
    return ""


@dataclass(frozen=True)
class RangeMatch:
    operator: str
    city_name: str | None = None
    region_name: str | None = None

    @property
    def apply_geo(self) -> bool:
        return self.city_name is not None or self.region_name is not None


@dataclass(frozen=True)
class OperatorRange:
    abc: str
    start: int
    end: int
    operator: str
    order: int = 0
    city_name: str | None = None
    region_name: str | None = None

    def covers(self, abc: str, local: int) -> bool:
        return self.abc == abc and self.start <= local <= self.end

    def as_match(self) -> RangeMatch:
        return RangeMatch(
            operator=self.operator,
            city_name=self.city_name,
            region_name=self.region_name,
        )


class OperatorRangeCache:
    """ABC-bucketed ranges; resolve uses bisect + first-insert-order among covering."""

    def __init__(self) -> None:
        self._by_abc: dict[str, list[OperatorRange]] = {}
        self._starts: dict[str, list[int]] = {}
        self._order = 0
        self._finalized = False

    def add(
        self,
        abc: str,
        start: int,
        end: int,
        operator: str,
        *,
        city_name: str | None = None,
        region_name: str | None = None,
    ) -> None:
        if not abc or not operator or end < start:
            return
        self._finalized = False
        bucket = self._by_abc.setdefault(abc, [])
        for idx, existing in enumerate(bucket):
            if existing.start == start and existing.end == end:
                if (city_name or region_name) and not (
                    existing.city_name or existing.region_name
                ):
                    bucket[idx] = OperatorRange(
                        abc=existing.abc,
                        start=existing.start,
                        end=existing.end,
                        operator=existing.operator,
                        order=existing.order,
                        city_name=city_name,
                        region_name=region_name,
                    )
                return
        self._order += 1
        bucket.append(
            OperatorRange(
                abc=abc,
                start=start,
                end=end,
                operator=operator,
                order=self._order,
                city_name=city_name,
                region_name=region_name,
            )
        )

    def add_from_api_row(self, row: dict) -> str | None:
        abc = str(row.get("abc") or "").strip()
        operator = str(row.get("operator") or "").strip()
        city_name, region_name = parse_gar_territory(row.get("garTerritory"))
        try:
            start = int(row["rangeStart"])
            end = int(row["rangeEnd"])
        except (KeyError, TypeError, ValueError):
            return operator or None
        if operator:
            self.add(
                abc,
                start,
                end,
                operator,
                city_name=city_name,
                region_name=region_name,
            )
        return operator or None

    def finalize(self) -> None:
        self._starts = {}
        for abc, bucket in self._by_abc.items():
            bucket.sort(key=lambda r: (r.start, r.end, r.order))
            self._starts[abc] = [r.start for r in bucket]
        self._finalized = True

    def resolve_parts(self, abc: str, local: int) -> RangeMatch | None:
        if not self._finalized:
            self.finalize()
        bucket = self._by_abc.get(abc) or []
        if not bucket:
            return None
        starts = self._starts.get(abc) or []
        i = bisect_right(starts, local) - 1
        best: RangeMatch | None = None
        best_order: int | None = None
        while i >= 0:
            r = bucket[i]
            if r.start <= local <= r.end:
                if best_order is None or r.order < best_order:
                    best = r.as_match()
                    best_order = r.order
            i -= 1
        return best

    def resolve(self, msisdn: str) -> RangeMatch | None:
        parts = parse_msisdn_parts(msisdn)
        if not parts:
            return None
        abc, local = parts
        return self.resolve_parts(abc, local)

    def resolve_linear_first_match(self, msisdn: str) -> RangeMatch | None:
        """Reference semantics (insertion order) for tests."""
        parts = parse_msisdn_parts(msisdn)
        if not parts:
            return None
        abc, local = parts
        for r in sorted(self._by_abc.get(abc) or [], key=lambda x: x.order):
            if r.covers(abc, local):
                return r.as_match()
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
    Set operator (and GAR city/region when present) on currently present catalog rows.

    Primary: local pstn_inn_ranges_cache (enabled INNs).
    Secondary: PSTN lookup API for cache misses (always queued; overwrites existing operator).
    With only_missing=False (default / production): every present row is enriched.
    Terminal PSTN miss (found=false / empty / invalid MSISDN / HTTP 400|404|422)
    → «Нет в реестре» on operator, city_name, and region_name. Transport/5xx/auth
    errors are retried; unresolved ones remain uncovered (do not write sentinel,
    do not clear existing operator/geo) and fail coverage.
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


def _enqueue_catalog_update(
    pending_updates: list[tuple],
    *,
    catalog_id,
    operator: str,
    current_operator: str | None,
    current_city: str | None,
    current_region: str | None,
    city: str | None = None,
    region: str | None = None,
    apply_geo: bool | None = None,
) -> None:
    if apply_geo is None:
        apply_geo = city is not None or region is not None
    if not apply_geo:
        city = None
        region = None
    op_changed = current_operator != operator
    geo_changed = apply_geo and (current_city != city or current_region != region)
    if op_changed or geo_changed:
        pending_updates.append((catalog_id, operator, apply_geo, city, region))


def _bulk_update_operators(
    db: Session,
    pairs: list[tuple],
) -> int:
    """UPDATE operator and optional GAR geo for (id, operator, apply_geo, city, region)."""
    if not pairs:
        return 0
    ids = [p[0] for p in pairs]
    ops = [p[1] for p in pairs]
    apply_geo = [p[2] for p in pairs]
    cities = [p[3] for p in pairs]
    regions = [p[4] for p in pairs]
    stmt = text(
        """
        UPDATE numbers_catalog_normalized AS c
        SET operator = v.operator,
            city_name = CASE WHEN v.apply_geo THEN v.city ELSE c.city_name END,
            region_name = CASE WHEN v.apply_geo THEN v.region ELSE c.region_name END
        FROM unnest(:ids, :ops, :apply_geo, :cities, :regions)
            AS v(id, operator, apply_geo, city, region)
        WHERE c.id = v.id
        """
    ).bindparams(
        bindparam("ids", type_=ARRAY(PGUUID(as_uuid=True))),
        bindparam("ops", type_=ARRAY(Text())),
        bindparam("apply_geo", type_=ARRAY(Boolean())),
        bindparam("cities", type_=ARRAY(Text())),
        bindparam("regions", type_=ARRAY(Text())),
    )
    db.execute(
        stmt,
        {
            "ids": ids,
            "ops": ops,
            "apply_geo": apply_geo,
            "cities": cities,
            "regions": regions,
        },
    )
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
    seeded_with_gar = 0
    for row in local_ranges:
        cache.add_from_api_row(row)
        if str(row.get("garTerritory") or "").strip():
            seeded_with_gar += 1
    logger.warning(
        "PSTN enrich: seeded %s ranges from local INN cache, seeded_with_gar=%s",
        len(local_ranges),
        seeded_with_gar,
    )
    if local_ranges and seeded_with_gar == 0:
        logger.warning(
            "PSTN enrich: none of the seeded ranges have garTerritory — reload PSTN cache"
        )
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
        NumbersCatalogNormalized.city_name,
        NumbersCatalogNormalized.region_name,
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
    not_in_registry = 0

    # (id, msisdn, phone, current_operator, current_city, current_region)
    pending: list[tuple] = []
    invalid_msisdns: list[str] = []

    for idx, row in enumerate(rows):
        (
            catalog_id,
            msisdn,
            current_operator,
            abc_code,
            number_local,
            current_city,
            current_region,
        ) = row
        msisdn_s = msisdn or ""
        match: RangeMatch | None = None
        if abc_code and number_local is not None:
            try:
                match = cache.resolve_parts(str(abc_code).strip(), int(number_local))
            except (TypeError, ValueError):
                match = None
        if match is None:
            match = cache.resolve(msisdn_s)
        if match:
            cache_hits += 1
            _enqueue_catalog_update(
                pending_updates,
                catalog_id=catalog_id,
                operator=match.operator,
                current_operator=current_operator,
                current_city=current_city,
                current_region=current_region,
                city=match.city_name,
                region=match.region_name,
            )
        else:
            # Cache miss: always queue PSTN lookup (even if operator already set).
            phone = phone_for_lookup(msisdn_s)
            if not phone:
                invalid_msisdns.append(msisdn_s)
                _enqueue_catalog_update(
                    pending_updates,
                    catalog_id=catalog_id,
                    operator=contract.OPERATOR_NOT_IN_REGISTRY,
                    current_operator=current_operator,
                    current_city=current_city,
                    current_region=current_region,
                    city=contract.OPERATOR_NOT_IN_REGISTRY,
                    region=contract.OPERATOR_NOT_IN_REGISTRY,
                )
                if current_operator != contract.OPERATOR_NOT_IN_REGISTRY:
                    not_in_registry += 1
            else:
                pending.append(
                    (
                        catalog_id,
                        msisdn_s,
                        phone,
                        current_operator,
                        current_city,
                        current_region,
                    )
                )
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
    logger.warning(
        "PSTN enrich: cache_hits=%s pending_api=%s invalid_msisdn=%s",
        cache_hits,
        len(pending),
        len(invalid_msisdns),
    )

    sem = asyncio.Semaphore(concurrency)
    # Successful PSTN operators only. Terminal miss vs transport error are separate sets.
    lookup_result: dict[str, str] = {}
    absent_phones: set[str] = set()
    error_phones: set[str] = set()
    progress_lock = asyncio.Lock()

    def _phone_resolved(phone: str) -> bool:
        return phone in lookup_result or phone in absent_phones

    async def lookup_phone_row(
        phone: str,
        *,
        wave_num: int,
        wave_base: int,
        wave_total: int,
        wave_done_box: list[int],
    ) -> None:
        nonlocal lookups, errors
        async with sem:
            try:
                raw = await client.lookup_phone(phone)
                lookups += 1
                kind = classify_lookup_response(raw)
                if kind is LookupClass.absent:
                    absent_phones.add(phone)
                    error_phones.discard(phone)
                elif kind is LookupClass.error:
                    errors += 1
                    error_phones.add(phone)
                    logger.warning(
                        "Finenumbers lookup error phone=%s status=%s body=%s",
                        phone,
                        raw.status_code,
                        _body_snippet(raw),
                    )
                else:
                    body = raw.body_json if isinstance(raw.body_json, dict) else {}
                    data = body.get("data") if isinstance(body.get("data"), dict) else {}
                    op = cache.add_from_api_row(data)
                    cache.finalize()
                    if op:
                        lookup_result[phone] = op
                        error_phones.discard(phone)
                    else:
                        absent_phones.add(phone)
                        error_phones.discard(phone)
            except Exception:
                errors += 1
                error_phones.add(phone)
                logger.exception("Finenumbers lookup failed for %s", phone)
            finally:
                async with progress_lock:
                    wave_done_box[0] += 1
                    done = wave_done_box[0]
                    if done % _WAVE_PROGRESS_EVERY == 0 or done == wave_total:
                        _progress(
                            on_progress,
                            f"PSTN lookup, волна {wave_num}: {done}/{wave_total} запросов",
                            wave_base + done,
                            wave_base + wave_total,
                        )

    rounds = 0
    while pending and rounds < max_rounds:
        still: list[tuple] = []
        phones_needed: list[str] = []
        phone_seen: set[str] = set()

        for item in pending:
            catalog_id, msisdn_s, phone, current_operator, current_city, current_region = item
            match = cache.resolve(msisdn_s)
            if match is None:
                op_direct = lookup_result.get(phone)
                if op_direct:
                    match = RangeMatch(operator=op_direct)
            if match:
                cache_hits += 1
                _enqueue_catalog_update(
                    pending_updates,
                    catalog_id=catalog_id,
                    operator=match.operator,
                    current_operator=current_operator,
                    current_city=current_city,
                    current_region=current_region,
                    city=match.city_name,
                    region=match.region_name,
                )
                continue

            if phone in absent_phones:
                _enqueue_catalog_update(
                    pending_updates,
                    catalog_id=catalog_id,
                    operator=contract.OPERATOR_NOT_IN_REGISTRY,
                    current_operator=current_operator,
                    current_city=current_city,
                    current_region=current_region,
                    city=contract.OPERATOR_NOT_IN_REGISTRY,
                    region=contract.OPERATOR_NOT_IN_REGISTRY,
                )
                if current_operator != contract.OPERATOR_NOT_IN_REGISTRY:
                    not_in_registry += 1
                continue

            # Unresolved: first attempt or retry previous transport/5xx error.
            still.append(item)
            if phone not in phone_seen and not _phone_resolved(phone):
                phone_seen.add(phone)
                phones_needed.append(phone)
                error_phones.discard(phone)

        pending = still
        if not phones_needed:
            break

        rounds += 1
        logger.warning(
            "PSTN enrich round=%s pending=%s phones_needed=%s lookups_so_far=%s "
            "errors=%s cache_hits=%s",
            rounds,
            len(pending),
            len(phones_needed),
            lookups,
            errors,
            cache_hits,
        )
        wave_base = lookups
        wave_total = len(phones_needed)
        wave_done_box = [0]
        _progress(
            on_progress,
            f"PSTN lookup, волна {rounds}: 0/{wave_total} запросов",
            wave_base,
            wave_base + wave_total,
        )
        await asyncio.gather(
            *(
                lookup_phone_row(
                    p,
                    wave_num=rounds,
                    wave_base=wave_base,
                    wave_total=wave_total,
                    wave_done_box=wave_done_box,
                )
                for p in phones_needed
            )
        )

    uncovered_msisdns: list[str] = []
    for item in pending:
        catalog_id, msisdn_s, phone, current_operator, current_city, current_region = item
        match = cache.resolve(msisdn_s)
        if match is None:
            op_direct = lookup_result.get(phone)
            if op_direct:
                match = RangeMatch(operator=op_direct)
        if match:
            cache_hits += 1
            _enqueue_catalog_update(
                pending_updates,
                catalog_id=catalog_id,
                operator=match.operator,
                current_operator=current_operator,
                current_city=current_city,
                current_region=current_region,
                city=match.city_name,
                region=match.region_name,
            )
        elif phone in absent_phones:
            _enqueue_catalog_update(
                pending_updates,
                catalog_id=catalog_id,
                operator=contract.OPERATOR_NOT_IN_REGISTRY,
                current_operator=current_operator,
                current_city=current_city,
                current_region=current_region,
                city=contract.OPERATOR_NOT_IN_REGISTRY,
                region=contract.OPERATOR_NOT_IN_REGISTRY,
            )
            if current_operator != contract.OPERATOR_NOT_IN_REGISTRY:
                not_in_registry += 1
        else:
            # Transport/HTTP error after retries — keep existing operator, do not write sentinel.
            uncovered_msisdns.append(msisdn_s)
            if phone in error_phones:
                logger.warning(
                    "PSTN enrich unresolved after retries msisdn=%s phone=%s "
                    "(existing operator preserved)",
                    msisdn_s,
                    phone,
                )

    updated = 0
    write_total = len(pending_updates)
    _progress(on_progress, f"Запись операторов ({write_total})", 0, write_total or None)
    for i in range(0, len(pending_updates), batch_size):
        chunk = pending_updates[i : i + batch_size]
        try:
            updated += _bulk_update_operators(db, chunk)
        except Exception:
            logger.exception("Bulk operator update failed; falling back to row updates")
            for catalog_id, operator, apply_geo, city, region in chunk:
                db.execute(
                    text(
                        "UPDATE numbers_catalog_normalized "
                        "SET operator = :op, "
                        "city_name = CASE WHEN :apply_geo THEN :city ELSE city_name END, "
                        "region_name = CASE WHEN :apply_geo THEN :region ELSE region_name END "
                        "WHERE id = :id"
                    ),
                    {
                        "op": operator,
                        "apply_geo": apply_geo,
                        "city": city,
                        "region": region,
                        "id": catalog_id,
                    },
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
        "not_in_registry": not_in_registry,
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
