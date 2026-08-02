"""Sync orchestration — CONTRACT_BACKED provider calls + OPERATIONAL job/persist."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import InventoryKind, ProviderCode, SyncJobStatus, SyncJobType, SyncLogLevel
from app.models.providers import Provider
from app.models.sync import SyncJob
from app.modules.sync_engine.logging import log_job
from app.modules.sync_engine.modes import SyncMode
from app.modules.sync_engine.persist import (
    build_city_lookup,
    persist_cities,
    persist_regions,
    persist_sipout_numbers,
)
from app.providers.dto.common import ConnectionConfig
from app.providers.dto.numbers import NormalizedNumber
from app.providers.errors import ProviderCapabilityLimitedError, ProviderError
from app.providers.registry import get_provider


def _job_type_for_mode(mode: SyncMode) -> SyncJobType:
    return SyncJobType(mode.value)


class SyncService:
    def __init__(self, db: Session):
        self.db = db

    def _get_provider_row(self, code: str) -> Provider:
        row = self.db.scalar(select(Provider).where(Provider.code == ProviderCode(code)))
        if not row:
            raise ProviderError(f"Provider not found in DB: {code}")
        return row

    def _connection_config(self, provider: Provider) -> ConnectionConfig:
        conn = provider.connection
        if not conn:
            raise ProviderError(f"No connection settings for provider {provider.code.value}")
        return ConnectionConfig(
            base_url=conn.base_url,
            auth_settings=conn.auth_settings or {},
            extra_settings=conn.extra_settings or {},
        )

    def start_and_run(
        self,
        provider_code: str,
        mode: SyncMode,
        *,
        dry_run: bool = False,
        include_dictionaries: bool = False,
        triggered_by: str = "api",
    ) -> SyncJob:
        provider = self._get_provider_row(provider_code)
        adapter = get_provider(provider.code)
        caps = adapter.capabilities()
        if mode == SyncMode.free_only and not caps.get("free_numbers", {}).get("supported"):
            raise ProviderCapabilityLimitedError(
                f"{provider_code} free_numbers not supported by uploaded docs",
                provider=provider_code,
                capability="free_numbers",
                doc_refs=caps.get("free_numbers", {}).get("doc_refs", []),
            )
        if mode == SyncMode.purchased_only and not caps.get("purchased_numbers", {}).get("supported"):
            raise ProviderCapabilityLimitedError(
                f"{provider_code} purchased_numbers not supported by uploaded docs",
                provider=provider_code,
                capability="purchased_numbers",
                doc_refs=caps.get("purchased_numbers", {}).get("doc_refs", []),
            )

        job = SyncJob(
            provider_id=provider.id,
            job_type=_job_type_for_mode(mode),
            status=SyncJobStatus.pending,
            triggered_by=triggered_by,
            stats={"dry_run": dry_run, "mode": mode.value},
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return self.run_job(job.id, include_dictionaries=include_dictionaries)

    def run_job(self, job_id: uuid.UUID, *, include_dictionaries: bool = False) -> SyncJob:
        job = self.db.get(SyncJob, job_id)
        if not job:
            raise ProviderError("Sync job not found")
        provider = self.db.get(Provider, job.provider_id)
        assert provider is not None
        adapter = get_provider(provider.code)
        connection = self._connection_config(provider)
        mode = SyncMode(job.job_type.value)
        dry_run = bool((job.stats or {}).get("dry_run"))

        job.status = SyncJobStatus.running
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()
        log_job(self.db, job.id, SyncLogLevel.info, f"Sync started mode={mode.value}")
        self.db.commit()

        stats: dict[str, Any] = {
            "dry_run": dry_run,
            "mode": mode.value,
            "limitations": [],
            "categories": {},
        }
        try:
            stats = asyncio.run(
                self._execute(
                    job=job,
                    provider=provider,
                    adapter=adapter,
                    connection=connection,
                    mode=mode,
                    dry_run=dry_run,
                    include_dictionaries=include_dictionaries,
                    stats=stats,
                )
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
            job.status = SyncJobStatus.failed
            job.error_summary = str(exc)
            log_job(self.db, job.id, SyncLogLevel.error, f"Sync failed: {exc}")
            self.db.commit()

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
        dry_run: bool,
        include_dictionaries: bool,
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        limitations: list[dict[str, Any]] = []
        city_lookup = build_city_lookup(self.db, provider.code.value)

        need_dict = mode in {SyncMode.full, SyncMode.dictionaries_only} or (
            include_dictionaries and mode in {SyncMode.free_only, SyncMode.purchased_only}
        )
        if need_dict:
            try:
                regions: list = []
                cities: list = []
                if provider.code == ProviderCode.sipout:
                    geo = await adapter.sync_cities(connection)
                    regions = (geo.items or {}).get("regions") if isinstance(geo.items, dict) else []
                    cities = (geo.items or {}).get("cities") if isinstance(geo.items, dict) else []
                else:
                    reg = await adapter.sync_regions(connection)
                    cit = await adapter.sync_cities(connection)
                    regions = (reg.items or {}).get("regions") if isinstance(reg.items, dict) else []
                    cities = (cit.items or {}).get("cities") if isinstance(cit.items, dict) else []
                if not dry_run:
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
                else:
                    stats["categories"]["dictionaries"] = {
                        "would_persist_regions": len(regions or []),
                        "would_persist_cities": len(cities or []),
                    }
                log_job(
                    self.db,
                    job.id,
                    SyncLogLevel.info,
                    "Dictionaries fetch completed",
                    {"regions": len(regions or []), "cities": len(cities or [])},
                )
                self.db.commit()
            except Exception as exc:
                log_job(self.db, job.id, SyncLogLevel.error, f"Dictionaries failed: {exc}")
                self.db.commit()
                stats["_fatal_error"] = str(exc)

        if mode in {SyncMode.full, SyncMode.free_only}:
            result = await adapter.sync_free_numbers(connection, city_lookup=city_lookup)
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
            elif isinstance(result.items, list):
                numbers = [x for x in result.items if isinstance(x, NormalizedNumber)]
                if dry_run:
                    stats["categories"]["free_numbers"] = {"would_upsert": len(numbers)}
                elif provider.code == ProviderCode.sipout:
                    stats["categories"]["free_numbers"] = persist_sipout_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.free,
                        numbers=numbers,
                        soft_absence=True,
                    )
                log_job(self.db, job.id, SyncLogLevel.info, f"Free numbers fetched={result.fetched}")
            self.db.commit()

        if mode in {SyncMode.full, SyncMode.purchased_only}:
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
            elif isinstance(result.items, list):
                numbers = [x for x in result.items if isinstance(x, NormalizedNumber)]
                if dry_run:
                    stats["categories"]["purchased_numbers"] = {"would_upsert": len(numbers)}
                elif provider.code == ProviderCode.sipout:
                    stats["categories"]["purchased_numbers"] = persist_sipout_numbers(
                        self.db,
                        provider_id=provider.id,
                        job_id=job.id,
                        inventory_kind=InventoryKind.purchased,
                        numbers=numbers,
                        soft_absence=True,
                    )
                log_job(
                    self.db, job.id, SyncLogLevel.info, f"Purchased numbers fetched={result.fetched}"
                )
            self.db.commit()

        stats["limitations"] = limitations
        return stats
