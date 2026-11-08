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
    persist_finenumbers_reg_purchased,
    persist_regions,
    persist_runexis_numbers,
    persist_sipout_numbers,
    persist_uis_numbers,
    persist_novofon_numbers,
    preserve_operators_on_numbers,
)
from app.modules.sync_engine.progress import SyncAborted, SyncProgressTracker, stage_for_provider_phase
from app.modules.sync_engine.safety import (
    confirmed_empty_slice,
    count_unique_provider_keys,
    record_slice_error,
    reload_allowed,
)
from app.providers.dto.common import ConnectionConfig
from app.providers.dto.numbers import NormalizedNumber
from app.providers.errors import ProviderError
from app.providers.registry import get_provider
from app.services.providers_service import persist_auth_settings


def _empty_stage_detail(base: str, result: Any) -> str:
    """Append account and shop notes without turning the slice into a warning."""
    extra = getattr(result, "extra_stats", None)
    if not isinstance(extra, dict):
        return base
    text = base
    principal = extra.get("principal")
    if isinstance(principal, dict):
        summary = principal.get("summary")
        if isinstance(summary, str) and summary.strip():
            text = f"{text}. {summary.strip()}"
    suffix = extra.get("empty_suffix")
    if isinstance(suffix, str) and suffix.strip():
        text = f"{text}. {suffix.strip()}"
    return text


def refuse_slice_detail(result: Any, *, reason: str | None, incoming: int) -> str:
    """Stage text when wipe is refused. A provider refusal_detail replaces the generic reason."""
    extra = getattr(result, "extra_stats", None)
    if isinstance(extra, dict):
        custom = extra.get("refusal_detail")
        if isinstance(custom, str) and custom.strip():
            return custom.strip()
    detail = reason or "refused wipe"
    fetched = int(getattr(result, "fetched", 0) or 0)
    if fetched > incoming:
        detail = f"{detail}; fetched={fetched} mapped={incoming}"
    integrity = extra.get("integrity") if isinstance(extra, dict) else None
    if isinstance(integrity, dict) and integrity.get("total_items_mismatch"):
        detail = f"{detail}; total_items={integrity.get('total_items')}"
    return detail


def _exc_summary(exc: BaseException, *, limit: int = 2000) -> str:
    """Include exception type so bare NoSuchTableError names are actionable in the UI."""
    return f"{type(exc).__name__}: {exc}"[:limit]


def _with_stage_note(detail: str, result: Any) -> str:
    """Append a provider note that is not a warning and must not refuse the slice."""
    extra = getattr(result, "extra_stats", None)
    if isinstance(extra, dict):
        note = extra.get("stage_note")
        if isinstance(note, str) and note.strip():
            return f"{detail}. {note.strip()}"
    return detail


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


def _log_page_integrity(
    db: Session,
    job_id: uuid.UUID,
    *,
    phase: str,
    extra_stats: dict[str, Any] | None,
) -> None:
    if not extra_stats:
        return
    integrity = extra_stats.get("integrity")
    if not isinstance(integrity, dict):
        return
    mismatch = bool(integrity.get("total_items_mismatch"))
    level = SyncLogLevel.warning if mismatch else SyncLogLevel.info
    log_job(db, job_id, level, f"{phase} integrity {integrity}", integrity)


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
        except SyncAborted:
            raise
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

        def _slice_integrity(result: Any) -> dict[str, Any] | None:
            extra = result.extra_stats if isinstance(result.extra_stats, dict) else {}
            integrity = extra.get("integrity")
            return integrity if isinstance(integrity, dict) else None

        def _confirmed_empty(result: Any, *, previous: int, incoming: int) -> bool:
            return confirmed_empty_slice(
                previous=previous,
                incoming=incoming,
                fetched=int(result.fetched or 0),
                warnings=list(result.warnings or []),
                integrity=_slice_integrity(result),
            )

        def _refuse_detail(result: Any, *, reason: str | None, incoming: int) -> str:
            return refuse_slice_detail(result, reason=reason, incoming=incoming)

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

            try:
                result = await adapter.sync_free_numbers(
                    connection,
                    city_lookup=city_lookup,
                    on_progress=_free_progress,
                )
            except ProviderError as exc:
                summary = _exc_summary(exc)
                record_slice_error(stats, summary)
                log_job(
                    self.db,
                    job.id,
                    SyncLogLevel.error,
                    f"Free numbers failed: {summary}",
                )
                self.db.commit()
                await _hook("free", "fail", summary)
                result = None
            if result is not None:
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
                        if _confirmed_empty(result, previous=previous, incoming=unique_incoming):
                            empty_detail = _empty_stage_detail(
                                "API вернул 0 свободных номеров", result
                            )
                            stats["categories"]["free_numbers"] = {
                                "accepted_empty": True,
                                "previous": previous,
                                "incoming": 0,
                                "fetched": int(result.fetched or 0),
                                "upserted": 0,
                                "reason": empty_detail,
                            }
                            if result.extra_stats:
                                stats["categories"]["free_numbers"].update(result.extra_stats)
                            log_job(self.db, job.id, SyncLogLevel.info, empty_detail)
                            self.db.commit()
                            await _hook("free", "end", empty_detail)
                        else:
                            detail = _refuse_detail(
                                result, reason=reason, incoming=unique_incoming
                            )
                            stats["categories"]["free_numbers"] = {
                                "refused_wipe": True,
                                "previous": previous,
                                "incoming": unique_incoming,
                                "incoming_raw": len(numbers),
                                "fetched": result.fetched,
                                "reason": detail,
                            }
                            record_slice_error(stats, detail)
                            log_job(self.db, job.id, SyncLogLevel.error, detail)
                            self.db.commit()
                            await _hook("free", "fail", detail)
                    else:
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
                        elif provider.code == ProviderCode.novofon:
                            persist_stats = persist_novofon_numbers(
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
                        free_detail = _with_stage_note(
                            _number_reload_detail(
                                fetched=fetched,
                                parsed=parsed,
                                upserted=int(persist_stats.get("upserted") or 0),
                            ),
                            result,
                        )
                        log_job(self.db, job.id, SyncLogLevel.info, f"Free numbers {free_detail}")
                        _log_page_integrity(
                            self.db, job.id, phase="Free", extra_stats=result.extra_stats
                        )
                        # Free cutover is committed; purchased failure after this = split inventory.
                        stats["_free_cutover_committed"] = True
                        free_block["operators_preserved"] = preserved_ops
                        self.db.commit()
                        await _hook("free", "end", free_detail)
                else:
                    self.db.commit()
                    await _hook("free", "end", _with_stage_note(f"fetched={result.fetched}", result))

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

                if provider.code == ProviderCode.finenumbers:
                    record_number_drops(
                        provider=provider.code.value,
                        inventory_kind=InventoryKind.purchased.value,
                        unmapped_raw=list(result.unmapped_raw or []),
                        numbers=numbers,
                    )
                    persist_progress = _throttled_persist_progress(
                        self.db,
                        job_id=job.id,
                        provider_code=provider.code.value,
                        phase="purchased",
                    )
                    await _purchased_progress("REG → купленные + РТУ", 0, unique_incoming)
                    log_job(
                        self.db,
                        job.id,
                        SyncLogLevel.info,
                        (
                            f"Finenumbers REG purchased+RTU raw={len(numbers)} "
                            f"unique={unique_incoming} (previous_fn={previous})"
                        ),
                    )
                    persist_stats = persist_finenumbers_reg_purchased(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        numbers=numbers,
                        on_progress=persist_progress,
                    )
                    parsed = int(result.parsed) if result.parsed else len(numbers)
                    fetched = int(result.fetched)
                    stats["categories"]["purchased_numbers"] = {
                        **_number_reload_stats(
                            fetched=fetched,
                            parsed=parsed,
                            persist_stats=persist_stats,
                            previous=previous,
                        ),
                        "reg_total": persist_stats.get("reg_total"),
                        "reg_inserted": persist_stats.get("reg_inserted"),
                        "reg_keys": persist_stats.get("reg_keys") or [],
                        "rtu_own": persist_stats.get("rtu_own"),
                        "rtu_external": persist_stats.get("rtu_external"),
                        "rtu_not_connected": persist_stats.get("rtu_not_connected"),
                    }
                    purch_detail = (
                        f"{_number_reload_detail(fetched=fetched, parsed=parsed, upserted=int(persist_stats.get('upserted') or 0))}; "
                        f"reg_inserted={persist_stats.get('reg_inserted')}, "
                        f"rtu_own={persist_stats.get('rtu_own')}, "
                        f"rtu_external={persist_stats.get('rtu_external')}, "
                        f"rtu_not_connected={persist_stats.get('rtu_not_connected')}"
                    )
                    log_job(
                        self.db, job.id, SyncLogLevel.info, f"Purchased numbers {purch_detail}"
                    )
                    self.db.commit()
                    await _hook("purchased", "end", purch_detail)
                else:
                    ok, reason = reload_allowed(
                        previous=previous, incoming=unique_incoming, kind="purchased"
                    )
                    if not ok:
                        if _confirmed_empty(
                            result, previous=previous, incoming=unique_incoming
                        ):
                            empty_detail = _empty_stage_detail(
                                "API вернул 0 купленных номеров", result
                            )
                            stats["categories"]["purchased_numbers"] = {
                                "accepted_empty": True,
                                "previous": previous,
                                "incoming": 0,
                                "fetched": int(result.fetched or 0),
                                "upserted": 0,
                                "reason": empty_detail,
                            }
                            if result.extra_stats:
                                stats["categories"]["purchased_numbers"].update(result.extra_stats)
                            log_job(self.db, job.id, SyncLogLevel.info, empty_detail)
                            self.db.commit()
                            await _hook("purchased", "end", empty_detail)
                        else:
                            detail = _refuse_detail(
                                result, reason=reason, incoming=unique_incoming
                            )
                            if stats.get("_free_cutover_committed"):
                                stats["_inventory_split"] = True
                                stats["inventory_split"] = True
                                detail = (
                                    f"{detail}; free inventory already cut over — "
                                    "catalog may be split (new free + previous purchased)"
                                )
                            stats["categories"]["purchased_numbers"] = {
                                "refused_wipe": True,
                                "previous": previous,
                                "incoming": unique_incoming,
                                "incoming_raw": len(numbers),
                                "fetched": result.fetched,
                                "reason": detail,
                            }
                            record_slice_error(stats, detail)
                            log_job(self.db, job.id, SyncLogLevel.error, detail)
                            self.db.commit()
                            await _hook("purchased", "fail", detail)
                    else:
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
                        elif provider.code == ProviderCode.novofon:
                            persist_stats = persist_novofon_numbers(
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
                        purch_block = _number_reload_stats(
                            fetched=fetched,
                            parsed=parsed,
                            persist_stats=persist_stats,
                            previous=previous,
                        )
                        if result.extra_stats:
                            purch_block.update(result.extra_stats)
                        stats["categories"]["purchased_numbers"] = purch_block
                        purch_detail = _number_reload_detail(
                            fetched=fetched,
                            parsed=parsed,
                            upserted=int(persist_stats.get("upserted") or 0),
                        )
                        log_job(
                            self.db, job.id, SyncLogLevel.info, f"Purchased numbers {purch_detail}"
                        )
                        _log_page_integrity(
                            self.db, job.id, phase="Purchased", extra_stats=result.extra_stats
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
