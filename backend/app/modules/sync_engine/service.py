"""Sync orchestration — CONTRACT_BACKED provider calls + OPERATIONAL job/persist."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.enums import InventoryKind, ProviderCode, SyncJobStatus, SyncLogLevel
from app.models.providers import Provider
from app.models.sync import SyncJob
from app.modules.sync_engine.dropped_export import record_number_drops
from app.modules.sync_engine.logging import log_job
from app.modules.sync_engine.modes import SyncMode
from app.modules.sync_engine.persist import (
    build_city_lookup,
    count_present_numbers,
    persist_aurora_numbers,
    persist_cities,
    persist_exolve_categories,
    persist_exolve_numbers,
    persist_voximplant_categories,
    persist_voximplant_numbers,
    persist_mcn_numbers,
    persist_finenumbers_numbers,
    persist_regions,
    persist_runexis_numbers,
    persist_sipout_numbers,
    persist_uis_numbers,
    preserve_operators_on_numbers,
)
from app.modules.sync_engine.progress import SyncProgressTracker, stage_for_provider_phase
from app.modules.sync_engine.safety import count_unique_provider_keys, reload_allowed
from app.providers.dto.common import ConnectionConfig
from app.providers.dto.numbers import NormalizedNumber
from app.providers.errors import ProviderError
from app.providers.registry import get_provider
from app.services.providers_service import persist_auth_settings


def _exc_summary(exc: BaseException, *, limit: int = 2000) -> str:
    """Include exception type so bare NoSuchTableError names are actionable in the UI."""
    return f"{type(exc).__name__}: {exc}"[:limit]


def _number_reload_detail(
    *,
    fetched: int,
    parsed: int,
    upserted: int,
) -> str:
    """Human-readable free/purchased stage summary with drop breakdown."""
    unmapped = max(0, int(fetched) - int(parsed))
    duplicates = max(0, int(parsed) - int(upserted))
    return (
        f"fetched={fetched}, parsed={parsed}, upserted={upserted}, "
        f"unmapped_dropped={unmapped}, duplicates_dropped={duplicates}"
    )


def _number_reload_stats(
    *,
    fetched: int,
    parsed: int,
    persist_stats: dict[str, Any],
    previous: int,
) -> dict[str, Any]:
    upserted = int(persist_stats.get("upserted") or 0)
    deduped = persist_stats.get("deduped_input")
    if deduped is not None:
        upserted_for_dupes = int(deduped)
    else:
        upserted_for_dupes = upserted
    unmapped = max(0, int(fetched) - int(parsed))
    duplicates = max(0, int(parsed) - upserted_for_dupes)
    return {
        **persist_stats,
        "previous": previous,
        "fetched": fetched,
        "parsed": parsed,
        "unmapped_dropped": unmapped,
        "duplicates_dropped": duplicates,
    }


def _throttled_persist_progress(
    db: Session,
    *,
    job_id: uuid.UUID,
    provider_code: str,
    phase: str,
) -> Callable[[str, int | None, int | None], Any]:
    """Side-session job log + UI progress — never touch the persist Session."""
    last = [0.0]
    run_id_raw = None
    job = db.get(SyncJob, job_id)
    if job and isinstance(job.stats, dict):
        run_id_raw = job.stats.get("sync_run_id")
    stage_id = stage_for_provider_phase(provider_code, phase)

    def _cb(detail: str, current: int | None = None, total: int | None = None) -> None:
        text = f"{detail} ({current}/{total})" if total is not None else str(detail)
        now = time.monotonic()
        force = "cutover" in text.lower() or "done" in text.lower()
        update_ui = bool(stage_id and run_id_raw) and (
            force or (now - last[0]) >= 1.0
        )
        if update_ui:
            last[0] = now
        side_db = SessionLocal()
        try:
            log_job(side_db, job_id, SyncLogLevel.info, text)
            side_db.commit()
            if update_ui:
                SyncProgressTracker(side_db, UUID(str(run_id_raw))).progress(
                    stage_id,
                    detail=detail or "",
                    substage=detail or "",
                    current=current,
                    total=total,
                    unit="numbers",
                )
        except Exception:
            try:
                side_db.rollback()
            except Exception:
                pass
        finally:
            side_db.close()

    return _cb


class SyncService:
    def __init__(self, db: Session):
        self.db = db

    def _connection_config(self, provider: Provider) -> ConnectionConfig:
        conn = provider.connection
        if not conn:
            raise ProviderError(f"No connection settings for provider {provider.code.value}")
        return ConnectionConfig(
            base_url=conn.base_url,
            auth_settings=dict(conn.auth_settings or {}),
            extra_settings=conn.extra_settings or {},
        )

    async def run_job_async(
        self,
        job_id: uuid.UUID,
        *,
        phase_hook: Any | None = None,
    ) -> SyncJob:
        """Run a provider job created by unified sync (stage+atomic cutover)."""
        job = self.db.get(SyncJob, job_id)
        if not job:
            raise ProviderError("Sync job not found")
        provider = self.db.get(Provider, job.provider_id)
        assert provider is not None
        adapter = get_provider(provider.code)
        connection = self._connection_config(provider)
        try:
            mode = SyncMode(job.job_type.value)
        except ValueError as exc:
            raise ProviderError(
                f"Unsupported sync job type for Wave-2 engine: {job.job_type.value}"
            ) from exc

        job.status = SyncJobStatus.running
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()
        log_job(self.db, job.id, SyncLogLevel.info, f"Sync started mode={mode.value}")
        self.db.commit()

        stats: dict[str, Any] = {
            "mode": mode.value,
            "limitations": [],
            "categories": {},
        }
        try:
            stats = await self._execute(
                job=job,
                provider=provider,
                adapter=adapter,
                connection=connection,
                mode=mode,
                stats=stats,
                phase_hook=phase_hook,
            )
            limitations = stats.get("limitations") or []
            cats = stats.get("categories") or {}
            if stats.get("_fatal_error"):
                job.status = SyncJobStatus.failed
                job.error_summary = stats.get("_fatal_error")
            elif limitations and cats:
                job.status = SyncJobStatus.partial
            elif limitations and not cats:
                job.status = SyncJobStatus.partial
            else:
                job.status = SyncJobStatus.success
        except Exception as exc:
            self.db.rollback()
            job = self.db.get(SyncJob, job_id)
            assert job is not None
            job.status = SyncJobStatus.failed
            summary = _exc_summary(exc)
            if stats.get("_free_cutover_committed"):
                summary = (
                    f"{summary}; free inventory already cut over — "
                    "catalog may be split (new free + previous purchased)"
                )
                stats["inventory_split"] = True
            job.error_summary = summary
            job.finished_at = datetime.now(timezone.utc)
            job.stats = {
                k: v for k, v in stats.items() if not str(k).startswith("_")
            }
            log_job(
                self.db, job.id, SyncLogLevel.error, f"Sync failed: {summary}"
            )
            self.db.commit()
            return job
        finally:
            try:
                provider = self.db.get(Provider, job.provider_id) or provider
                if provider is not None and provider.connection is not None:
                    persist_auth_settings(provider.connection, connection.auth_settings)
                    self.db.commit()
            except Exception:
                self.db.rollback()

        public_stats = {k: v for k, v in stats.items() if not str(k).startswith("_")}
        if stats.get("_inventory_split"):
            public_stats["inventory_split"] = True
        job.stats = public_stats
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    async def _execute(
        self,
        *,
        job: SyncJob,
        provider: Provider,
        adapter: Any,
        connection: ConnectionConfig,
        mode: SyncMode,
        stats: dict[str, Any],
        phase_hook: Any | None = None,
    ) -> dict[str, Any]:
        async def _hook(
            phase: str,
            event: str,
            detail: str = "",
            *,
            current: int | None = None,
            total: int | None = None,
        ) -> None:
            if phase_hook is None:
                return
            try:
                await phase_hook(phase, event, detail, current=current, total=total)
            except TypeError:
                await phase_hook(phase, event, detail)

        limitations: list[dict[str, Any]] = []
        city_lookup = build_city_lookup(self.db, provider.code.value)

        # full → dictionaries + free + purchased; free_only → free only
        if mode == SyncMode.full:
            dict_supported = bool(
                adapter.capabilities().get("dictionaries", {}).get("supported")
            )
            if not dict_supported:
                stats["categories"]["dictionaries"] = {"limited": True}
                await _hook("dictionaries", "skip", "capability not supported")
            else:
                await _hook("dictionaries", "begin")

                async def _dict_progress(
                    detail: str, current: int | None = None, total: int | None = None
                ) -> None:
                    await _hook(
                        "dictionaries", "progress", detail, current=current, total=total
                    )

                try:
                    regions: list = []
                    cities: list = []
                    categories: list = []
                    if provider.code == ProviderCode.sipout:
                        geo = await adapter.sync_cities(
                            connection, on_progress=_dict_progress
                        )
                        regions = (
                            (geo.items or {}).get("regions")
                            if isinstance(geo.items, dict)
                            else []
                        )
                        cities = (
                            (geo.items or {}).get("cities")
                            if isinstance(geo.items, dict)
                            else []
                        )
                    elif provider.code in (
                        ProviderCode.exolve,
                        ProviderCode.voximplant,
                        ProviderCode.mcn,
                    ):
                        geo = await adapter.sync_regions(
                            connection, on_progress=_dict_progress
                        )
                        regions = (
                            (geo.items or {}).get("regions")
                            if isinstance(geo.items, dict)
                            else []
                        )
                        cities = (
                            (geo.items or {}).get("cities")
                            if isinstance(geo.items, dict)
                            else []
                        )
                        categories = (
                            (geo.items or {}).get("categories")
                            if isinstance(geo.items, dict)
                            else []
                        )
                    else:
                        reg = await adapter.sync_regions(
                            connection, on_progress=_dict_progress
                        )
                        cit = await adapter.sync_cities(
                            connection, on_progress=_dict_progress
                        )
                        regions = (
                            (reg.items or {}).get("regions")
                            if isinstance(reg.items, dict)
                            else []
                        )
                        cities = (
                            (cit.items or {}).get("cities")
                            if isinstance(cit.items, dict)
                            else []
                        )
                        categories = []
                    await _dict_progress("Запись справочников")
                    rc = persist_regions(
                        self.db,
                        provider_code=provider.code.value,
                        job_id=job.id,
                        regions=regions or [],
                    )
                    cc = persist_cities(
                        self.db,
                        provider_code=provider.code.value,
                        job_id=job.id,
                        cities=cities or [],
                    )
                    cat_n = 0
                    if provider.code == ProviderCode.exolve and categories:
                        cat_n = persist_exolve_categories(
                            self.db, job_id=job.id, categories=categories
                        )
                    elif provider.code == ProviderCode.voximplant and categories:
                        cat_n = persist_voximplant_categories(
                            self.db, job_id=job.id, categories=categories
                        )
                    stats["categories"]["dictionaries"] = {
                        "regions": rc,
                        "cities": cc,
                        **({"categories": cat_n} if cat_n else {}),
                    }
                    city_lookup = build_city_lookup(self.db, provider.code.value)
                    log_job(
                        self.db,
                        job.id,
                        SyncLogLevel.info,
                        "Dictionaries fetch completed",
                        {"regions": len(regions or []), "cities": len(cities or [])},
                    )
                    self.db.commit()
                    await _hook(
                        "dictionaries",
                        "end",
                        f"regions={len(regions or [])}, cities={len(cities or [])}",
                    )
                except Exception as exc:
                    summary = _exc_summary(exc)
                    log_job(
                        self.db, job.id, SyncLogLevel.error, f"Dictionaries failed: {summary}"
                    )
                    self.db.commit()
                    stats["_fatal_error"] = summary
                    await _hook("dictionaries", "fail", summary)
                    stats["limitations"] = limitations
                    return stats

        if mode in {SyncMode.full, SyncMode.free_only}:
            await _hook("free", "begin")

            async def _free_progress(
                detail: str, current: int | None = None, total: int | None = None
            ) -> None:
                await _hook("free", "progress", detail, current=current, total=total)

            result = await adapter.sync_free_numbers(
                connection,
                city_lookup=city_lookup,
                on_progress=_free_progress,
            )
            for lim in result.limitations:
                limitations.append(
                    {
                        "provider": lim.provider,
                        "capability": lim.capability,
                        "message": lim.message,
                        "doc_refs": lim.doc_refs,
                    }
                )
                log_job(self.db, job.id, SyncLogLevel.warning, lim.message)
            if result.limitations and not result.items:
                stats["categories"]["free_numbers"] = {"limited": True}
                await _hook("free", "skip", "capability limited")
            elif isinstance(result.items, list):
                numbers = [x for x in result.items if isinstance(x, NormalizedNumber)]
                previous = count_present_numbers(
                    self.db,
                    provider_id=provider.id,
                    inventory_kind=InventoryKind.free,
                )
                unique_incoming = count_unique_provider_keys(numbers)
                ok, reason = reload_allowed(
                    previous=previous, incoming=unique_incoming, kind="free"
                )
                if not ok:
                    stats["categories"]["free_numbers"] = {
                        "refused_wipe": True,
                        "previous": previous,
                        "incoming": unique_incoming,
                        "incoming_raw": len(numbers),
                        "fetched": result.fetched,
                        "reason": reason,
                    }
                    stats["_fatal_error"] = reason
                    log_job(self.db, job.id, SyncLogLevel.error, reason or "refused wipe")
                    self.db.commit()
                    await _hook("free", "fail", reason or "refused wipe")
                    stats["limitations"] = limitations
                    return stats

                record_number_drops(
                    provider=provider.code.value,
                    inventory_kind=InventoryKind.free.value,
                    unmapped_raw=list(result.unmapped_raw or []),
                    numbers=numbers,
                )
                preserved_ops = preserve_operators_on_numbers(
                    self.db,
                    provider_id=provider.id,
                    inventory_kind=InventoryKind.free,
                    numbers=numbers,
                )
                persist_progress = _throttled_persist_progress(
                    self.db,
                    job_id=job.id,
                    provider_code=provider.code.value,
                    phase="free",
                )
                await _free_progress("Буфер → каталог", 0, unique_incoming)
                log_job(
                    self.db,
                    job.id,
                    SyncLogLevel.info,
                    (
                        f"Staging cutover provider={provider.code.value} kind=free "
                        f"reload unique={unique_incoming} raw={len(numbers)} "
                        f"(previous={previous}, operators_preserved={preserved_ops})"
                    ),
                )
                if provider.code == ProviderCode.sipout:
                    persist_stats = persist_sipout_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.runexis:
                    persist_stats = persist_runexis_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.uis:
                    persist_stats = persist_uis_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.aurora:
                    persist_stats = persist_aurora_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.exolve:
                    persist_stats = persist_exolve_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.voximplant:
                    persist_stats = persist_voximplant_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.mcn:
                    persist_stats = persist_mcn_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.finenumbers:
                    persist_stats = persist_finenumbers_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                else:
                    persist_stats = {}
                parsed = int(result.parsed) if result.parsed else len(numbers)
                fetched = int(result.fetched)
                free_block = _number_reload_stats(
                    fetched=fetched,
                    parsed=parsed,
                    persist_stats=persist_stats,
                    previous=previous,
                )
                if result.extra_stats:
                    free_block.update(result.extra_stats)
                stats["categories"]["free_numbers"] = free_block
                await _free_progress(
                    f"Записано {persist_stats.get('upserted', 0)}",
                    persist_stats.get("upserted"),
                    unique_incoming,
                )
                free_detail = _number_reload_detail(
                    fetched=fetched,
                    parsed=parsed,
                    upserted=int(persist_stats.get("upserted") or 0),
                )
                log_job(self.db, job.id, SyncLogLevel.info, f"Free numbers {free_detail}")
                if isinstance(result.extra_stats.get("integrity"), dict):
                    log_job(
                        self.db,
                        job.id,
                        SyncLogLevel.info,
                        f"Free integrity {result.extra_stats['integrity']}",
                        result.extra_stats["integrity"],
                    )
                # Free cutover is committed; purchased failure after this = split inventory.
                stats["_free_cutover_committed"] = True
                free_block["operators_preserved"] = preserved_ops
                self.db.commit()
                await _hook("free", "end", free_detail)
            else:
                self.db.commit()
                await _hook("free", "end", f"fetched={result.fetched}")

        purchased_supported = bool(
            adapter.capabilities().get("purchased_numbers", {}).get("supported")
        )
        if mode == SyncMode.full and purchased_supported:
            await _hook("purchased", "begin")

            async def _purchased_progress(
                detail: str, current: int | None = None, total: int | None = None
            ) -> None:
                await _hook(
                    "purchased", "progress", detail, current=current, total=total
                )

            result = await adapter.sync_purchased_numbers(
                connection,
                city_lookup=city_lookup,
                on_progress=_purchased_progress,
            )
            for lim in result.limitations:
                limitations.append(
                    {
                        "provider": lim.provider,
                        "capability": lim.capability,
                        "message": lim.message,
                        "doc_refs": lim.doc_refs,
                    }
                )
                log_job(self.db, job.id, SyncLogLevel.warning, lim.message)
            if result.limitations and not result.items:
                stats["categories"]["purchased_numbers"] = {"limited": True}
                await _hook("purchased", "skip", "capability limited")
            elif isinstance(result.items, list):
                numbers = [x for x in result.items if isinstance(x, NormalizedNumber)]
                previous = count_present_numbers(
                    self.db,
                    provider_id=provider.id,
                    inventory_kind=InventoryKind.purchased,
                )
                unique_incoming = count_unique_provider_keys(numbers)
                ok, reason = reload_allowed(
                    previous=previous, incoming=unique_incoming, kind="purchased"
                )
                if not ok:
                    stats["categories"]["purchased_numbers"] = {
                        "refused_wipe": True,
                        "previous": previous,
                        "incoming": unique_incoming,
                        "incoming_raw": len(numbers),
                        "fetched": result.fetched,
                        "reason": reason,
                    }
                    if stats.get("_free_cutover_committed"):
                        stats["_inventory_split"] = True
                        stats["inventory_split"] = True
                        split_msg = (
                            f"{reason}; free inventory already cut over — "
                            "catalog may be split (new free + previous purchased)"
                        )
                        stats["_fatal_error"] = split_msg
                        log_job(self.db, job.id, SyncLogLevel.error, split_msg)
                    else:
                        stats["_fatal_error"] = reason
                        log_job(
                            self.db, job.id, SyncLogLevel.error, reason or "refused wipe"
                        )
                    self.db.commit()
                    await _hook("purchased", "fail", stats["_fatal_error"] or "refused wipe")
                    stats["limitations"] = limitations
                    return stats

                record_number_drops(
                    provider=provider.code.value,
                    inventory_kind=InventoryKind.purchased.value,
                    unmapped_raw=list(result.unmapped_raw or []),
                    numbers=numbers,
                )
                preserve_operators_on_numbers(
                    self.db,
                    provider_id=provider.id,
                    inventory_kind=InventoryKind.purchased,
                    numbers=numbers,
                )
                persist_progress = _throttled_persist_progress(
                    self.db,
                    job_id=job.id,
                    provider_code=provider.code.value,
                    phase="purchased",
                )
                await _purchased_progress("Буфер → каталог", 0, unique_incoming)
                log_job(
                    self.db,
                    job.id,
                    SyncLogLevel.info,
                    (
                        f"Staging cutover provider={provider.code.value} kind=purchased "
                        f"reload unique={unique_incoming} raw={len(numbers)} "
                        f"(previous={previous})"
                    ),
                )
                if provider.code == ProviderCode.sipout:
                    persist_stats = persist_sipout_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.purchased,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.runexis:
                    persist_stats = persist_runexis_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.purchased,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                elif provider.code == ProviderCode.uis:
                    persist_stats = persist_uis_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.purchased,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                else:
                    persist_stats = {}
                parsed = int(result.parsed) if result.parsed else len(numbers)
                fetched = int(result.fetched)
                stats["categories"]["purchased_numbers"] = _number_reload_stats(
                    fetched=fetched,
                    parsed=parsed,
                    persist_stats=persist_stats,
                    previous=previous,
                )
                purch_detail = _number_reload_detail(
                    fetched=fetched,
                    parsed=parsed,
                    upserted=int(persist_stats.get("upserted") or 0),
                )
                log_job(
                    self.db, job.id, SyncLogLevel.info, f"Purchased numbers {purch_detail}"
                )
                self.db.commit()
                await _hook("purchased", "end", purch_detail)
            else:
                self.db.commit()
                await _hook("purchased", "end", f"fetched={result.fetched}")
        elif mode == SyncMode.full and not purchased_supported:
            await _hook("purchased", "skip", "capability not supported")

        stats["limitations"] = limitations
        return stats
