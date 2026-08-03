"""Sync orchestration — CONTRACT_BACKED provider calls + OPERATIONAL job/persist."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import InventoryKind, ProviderCode, SyncJobStatus, SyncLogLevel
from app.models.providers import Provider
from app.models.sync import SyncJob
from app.modules.sync_engine.logging import log_job
from app.modules.sync_engine.modes import SyncMode
from app.modules.sync_engine.persist import (
    build_city_lookup,
    count_present_numbers,
    persist_cities,
    persist_finenumbers_numbers,
    persist_regions,
    persist_runexis_numbers,
    persist_sipout_numbers,
    persist_uis_numbers,
)
from app.modules.sync_engine.safety import reload_allowed
from app.providers.dto.common import ConnectionConfig
from app.providers.dto.numbers import NormalizedNumber
from app.providers.errors import ProviderError
from app.providers.registry import get_provider
from app.services.providers_service import persist_auth_settings


def _exc_summary(exc: BaseException, *, limit: int = 2000) -> str:
    """Include exception type so bare NoSuchTableError names are actionable in the UI."""
    return f"{type(exc).__name__}: {exc}"[:limit]


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
            job.error_summary = _exc_summary(exc)
            job.finished_at = datetime.now(timezone.utc)
            log_job(
                self.db, job.id, SyncLogLevel.error, f"Sync failed: {_exc_summary(exc)}"
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

        job.stats = {k: v for k, v in stats.items() if not str(k).startswith("_")}
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
                try:
                    regions: list = []
                    cities: list = []
                    if provider.code == ProviderCode.sipout:
                        geo = await adapter.sync_cities(connection)
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
                    else:
                        reg = await adapter.sync_regions(connection)
                        cit = await adapter.sync_cities(connection)
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
                    stats["categories"]["dictionaries"] = {"regions": rc, "cities": cc}
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
                    await _hook("dictionaries", "fail", summary[:300])
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
                ok, reason = reload_allowed(
                    previous=previous, incoming=len(numbers), kind="free"
                )
                if not ok:
                    stats["categories"]["free_numbers"] = {
                        "refused_wipe": True,
                        "previous": previous,
                        "incoming": len(numbers),
                        "fetched": result.fetched,
                        "reason": reason,
                    }
                    stats["_fatal_error"] = reason
                    log_job(self.db, job.id, SyncLogLevel.error, reason or "refused wipe")
                    self.db.commit()
                    await _hook("free", "fail", reason or "refused wipe")
                    stats["limitations"] = limitations
                    return stats

                await _free_progress("Буфер → каталог…", 0, len(numbers))
                log_job(
                    self.db,
                    job.id,
                    SyncLogLevel.info,
                    (
                        f"Staging cutover provider={provider.code.value} kind=free "
                        f"reload {len(numbers)} (previous={previous})"
                    ),
                )
                if provider.code == ProviderCode.sipout:
                    persist_stats = persist_sipout_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=lambda d, c=None, t=None: log_job(
                            self.db,
                            job.id,
                            SyncLogLevel.info,
                            f"{d} ({c}/{t})" if t is not None else d,
                        ),
                    )
                elif provider.code == ProviderCode.runexis:
                    persist_stats = persist_runexis_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=lambda d, c=None, t=None: log_job(
                            self.db,
                            job.id,
                            SyncLogLevel.info,
                            f"{d} ({c}/{t})" if t is not None else d,
                        ),
                    )
                elif provider.code == ProviderCode.uis:
                    persist_stats = persist_uis_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=lambda d, c=None, t=None: log_job(
                            self.db,
                            job.id,
                            SyncLogLevel.info,
                            f"{d} ({c}/{t})" if t is not None else d,
                        ),
                    )
                elif provider.code == ProviderCode.finenumbers:
                    persist_stats = persist_finenumbers_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        on_progress=lambda d, c=None, t=None: log_job(
                            self.db,
                            job.id,
                            SyncLogLevel.info,
                            f"{d} ({c}/{t})" if t is not None else d,
                        ),
                    )
                else:
                    persist_stats = {}
                await _free_progress(
                    f"Записано {persist_stats.get('upserted', 0)}",
                    persist_stats.get("upserted"),
                    len(numbers),
                )
                stats["categories"]["free_numbers"] = {
                    **persist_stats,
                    "previous": previous,
                }
                log_job(
                    self.db,
                    job.id,
                    SyncLogLevel.info,
                    f"Free numbers fetched={result.fetched}",
                )
                self.db.commit()
                free_detail = f"fetched={result.fetched}"
                if isinstance(stats.get("categories", {}).get("free_numbers"), dict):
                    free_detail += (
                        f", upserted={stats['categories']['free_numbers'].get('upserted', 0)}"
                    )
                await _hook("free", "end", free_detail)
            else:
                self.db.commit()
                await _hook("free", "end", f"fetched={result.fetched}")

        purchased_supported = bool(
            adapter.capabilities().get("purchased_numbers", {}).get("supported")
        )
        if mode == SyncMode.full and purchased_supported:
            await _hook("purchased", "begin")
            result = await adapter.sync_purchased_numbers(connection, city_lookup=city_lookup)
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
                ok, reason = reload_allowed(
                    previous=previous, incoming=len(numbers), kind="purchased"
                )
                if not ok:
                    stats["categories"]["purchased_numbers"] = {
                        "refused_wipe": True,
                        "previous": previous,
                        "incoming": len(numbers),
                        "fetched": result.fetched,
                        "reason": reason,
                    }
                    stats["_fatal_error"] = reason
                    log_job(self.db, job.id, SyncLogLevel.error, reason or "refused wipe")
                    self.db.commit()
                    await _hook("purchased", "fail", reason or "refused wipe")
                    stats["limitations"] = limitations
                    return stats

                log_job(
                    self.db,
                    job.id,
                    SyncLogLevel.info,
                    (
                        f"Staging cutover provider={provider.code.value} kind=purchased "
                        f"reload {len(numbers)} (previous={previous})"
                    ),
                )
                if provider.code == ProviderCode.sipout:
                    persist_stats = persist_sipout_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.purchased,
                        numbers=numbers,
                    )
                elif provider.code == ProviderCode.runexis:
                    persist_stats = persist_runexis_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.purchased,
                        numbers=numbers,
                    )
                elif provider.code == ProviderCode.uis:
                    persist_stats = persist_uis_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.purchased,
                        numbers=numbers,
                    )
                else:
                    persist_stats = {}
                stats["categories"]["purchased_numbers"] = {
                    **persist_stats,
                    "previous": previous,
                }
                log_job(
                    self.db,
                    job.id,
                    SyncLogLevel.info,
                    f"Purchased numbers fetched={result.fetched}",
                )
                self.db.commit()
                purch_detail = f"fetched={result.fetched}"
                if isinstance(stats.get("categories", {}).get("purchased_numbers"), dict):
                    purch_detail += (
                        ", upserted="
                        f"{stats['categories']['purchased_numbers'].get('upserted', 0)}"
                    )
                await _hook("purchased", "end", purch_detail)
            else:
                self.db.commit()
                await _hook("purchased", "end", f"fetched={result.fetched}")
        elif mode == SyncMode.full and not purchased_supported:
            await _hook("purchased", "skip", "capability not supported")

        stats["limitations"] = limitations
        return stats
