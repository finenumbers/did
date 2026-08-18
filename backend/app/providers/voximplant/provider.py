"""Voximplant orchestrator. Docs: docs/providers/voximplant-contract.md."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.models.enums import InventoryKind, ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import (
    ConnectionConfig,
    DiagnosticsResult,
    SyncLimitation,
    SyncResult,
)
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.progress_emit import emit_progress
from app.providers.voximplant import contract, mapper, parser
from app.providers.voximplant.client import VoximplantClient

logger = logging.getLogger(__name__)


class VoximplantProvider(AbstractProvider):
    code = ProviderCode.voximplant

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "POST /platform_api/GetNewPhoneNumbers (RU category×region)",
                "doc_refs": contract.DOC_REFS_FREE,
            },
            "purchased_numbers": {
                "supported": False,
                "source": "out_of_scope_v1",
                "action": None,
            },
            "dictionaries": {
                "supported": True,
                "source": "documentation_verified",
                "actions": [
                    "POST /platform_api/GetPhoneNumberCategories",
                    "POST /platform_api/GetPhoneNumberRegions",
                ],
                "doc_refs": contract.DOC_REFS_REFERENCE,
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GetAccountInfo + GetPhoneNumberCategories RU",
                "doc_refs": contract.DOC_REFS_AUTH,
            },
        }

    def _client(self, connection: ConnectionConfig, **kwargs: Any) -> VoximplantClient:
        return VoximplantClient(connection, **kwargs)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = self._client(connection)
        account, raw_acc = await client.get_account_info()
        cats, raw_cats = await client.get_ru_categories()
        if not cats:
            return DiagnosticsResult(
                ok=False,
                message="Voximplant: no listable RU phone categories",
                checked_at=datetime.now(timezone.utc),
                details={"categories": 0, "currency": account.get("currency")},
                raw=raw_cats,
            )
        return DiagnosticsResult(
            ok=True,
            message="Voximplant OK",
            checked_at=datetime.now(timezone.utc),
            details={
                "categories": len(cats),
                "currency": account.get("currency"),
                "account_id": account.get("account_id"),
                "api_address": raw_acc.body_json.get("api_address")
                if isinstance(raw_acc.body_json, dict)
                else None,
            },
            raw=raw_cats,
        )

    async def _load_dictionaries(
        self, connection: ConnectionConfig, **kwargs: Any
    ) -> tuple[list, list, list[dict[str, Any]], list, dict[str, Any]]:
        on_progress = kwargs.get("on_progress")
        client = self._client(connection)
        await emit_progress(on_progress, "Voximplant: GetAccountInfo")
        account, acc_env = await client.get_account_info()
        await emit_progress(on_progress, "Voximplant: GetPhoneNumberCategories RU")
        categories, cat_env = await client.get_ru_categories()
        if not categories:
            raise ProviderError(
                "Voximplant: zero listable RU categories",
                code="VOXIMPLANT_EMPTY_CATEGORIES",
            )

        regions: list = []
        cities: list = []
        region_rows: list[dict[str, Any]] = []
        envelopes = [acc_env, cat_env]
        for idx, cat in enumerate(categories, start=1):
            name = str(cat["phone_category_name"])
            await emit_progress(
                on_progress,
                f"Voximplant regions {idx}/{len(categories)} {name}",
                idx,
                len(categories),
            )
            rows, env = await client.get_regions(name)
            envelopes.append(env)
            for row in rows:
                region, city = parser.parse_region_city(row, category=name)
                regions.append(region)
                cities.append(city)
                region_rows.append(row)

        if not regions:
            raise ProviderError(
                "Voximplant: zero RU regions across categories",
                code="VOXIMPLANT_EMPTY_REGIONS",
            )
        meta = {
            "currency": account.get("currency"),
            "categories": len(categories),
            "regions": len(regions),
            "region_rows": region_rows,
            "category_rows": categories,
        }
        return regions, cities, mapper.category_raw_rows(categories), envelopes, meta

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        regions, cities, categories, envelopes, meta = await self._load_dictionaries(
            connection, **kwargs
        )
        return SyncResult(
            fetched=len(regions),
            parsed=len(regions),
            items={
                "regions": regions,
                "cities": cities,
                "categories": categories,
            },
            raw_envelopes=envelopes,
            warnings=[
                f"categories={meta['categories']}",
                f"regions={meta['regions']}",
                f"currency={meta.get('currency')}",
            ],
            extra_stats={
                "integrity": {
                    "categories": meta["categories"],
                    "regions": meta["regions"],
                    "currency": meta.get("currency"),
                },
                "_vox_region_rows": meta["region_rows"],
                "_vox_category_rows": meta["category_rows"],
            },
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return await self.sync_regions(connection, **kwargs)

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        on_progress = kwargs.get("on_progress")
        client = self._client(connection)

        await emit_progress(on_progress, "Voximplant: справочники для плана free")
        account, acc_env = await client.get_account_info()
        categories, cat_env = await client.get_ru_categories()
        if not categories:
            raise ProviderError(
                "Voximplant free: zero listable RU categories",
                code="VOXIMPLANT_EMPTY_CATEGORIES",
            )

        slices: list[tuple[str, int, str | None, int | None]] = []
        envelopes = [acc_env, cat_env]
        for cat in categories:
            name = str(cat["phone_category_name"])
            rows, env = await client.get_regions(name)
            envelopes.append(env)
            for row in rows:
                try:
                    rid = int(row["phone_region_id"])
                except (KeyError, TypeError, ValueError):
                    continue
                count = row.get("phone_count")
                try:
                    phone_count = int(count) if count is not None else None
                except (TypeError, ValueError):
                    phone_count = None
                if phone_count is not None and phone_count <= 0:
                    continue
                rname = (
                    str(
                        row.get("localized_phone_region_name")
                        or row.get("phone_region_name")
                        or ""
                    ).strip()
                    or None
                )
                slices.append((name, rid, rname, phone_count))

        if not slices:
            raise ProviderError(
                "Voximplant free: no stock regions for RU categories",
                code="VOXIMPLANT_EMPTY_SLICES",
            )

        await emit_progress(
            on_progress,
            (
                f"Voximplant free: срезов={len(slices)} "
                f"categories={len(categories)}"
            ),
            0,
            len(slices),
        )
        logger.warning(
            "Voximplant free plan slices=%s categories=%s currency=%s",
            len(slices),
            [c.get("phone_category_name") for c in categories],
            account.get("currency"),
        )

        sem = asyncio.Semaphore(contract.MAX_SLICE_CONCURRENCY)
        all_items: list[dict[str, Any]] = []
        slice_metas: list[dict[str, Any]] = []
        lock = asyncio.Lock()
        done = 0

        async def _one(slice_row: tuple[str, int, str | None, int | None]) -> None:
            nonlocal done
            category, region_id, region_name, phone_count = slice_row
            async with sem:
                # Fan-out: suppress per-page details so slice counter stays coherent.
                items, envs, meta = await client.iter_free_slice(
                    category=category,
                    region_id=region_id,
                    region_name=region_name,
                    on_progress=None,
                    expected_phone_count=phone_count,
                )
            async with lock:
                all_items.extend(items)
                envelopes.extend(envs)
                slice_metas.append(meta)
                done += 1
                await emit_progress(
                    on_progress,
                    (
                        f"Voximplant free: срезы {done}/{len(slices)} "
                        f"{category} region={region_id}"
                    ),
                    done,
                    len(slices),
                )

        try:
            await asyncio.gather(*[_one(s) for s in slices])
        except (ProviderAuthError, ProviderError, ProviderTransportError):
            raise
        except Exception as exc:
            raise ProviderError(
                f"Voximplant free fan-out failed: {exc}",
                code="VOXIMPLANT_FANOUT_FAILED",
            ) from exc

        expected_total = sum(
            int(m["total_count"])
            for m in slice_metas
            if m.get("total_count") is not None
        )
        await emit_progress(
            on_progress, "Voximplant: разбор и маппинг", len(all_items), len(all_items)
        )
        mapped = []
        unmapped_raw: list[dict] = []
        for raw_item in all_items:
            category = str(raw_item.get("_vox_category") or "")
            region_id = int(raw_item.get("_vox_region_id"))
            parsed = parser.parse_number_item(
                raw_item,
                category=category,
                region_id=region_id,
                region_name=raw_item.get("_vox_region_name"),
            )
            num = mapper.map_number(parsed, inventory_kind=InventoryKind.free)
            if num:
                mapped.append(num)
            else:
                unmapped_raw.append(raw_item)

        seen: set[str] = set()
        deduped = []
        for num in mapped:
            key = num.provider_number_key or ""
            if key in seen:
                continue
            seen.add(key)
            deduped.append(num)
        mapped = deduped

        integrity = {
            "categories": len(categories),
            "slices_planned": len(slices),
            "slices_done": len(slice_metas),
            "fetched_raw": len(all_items),
            "unique_keys": len(mapped),
            "map_failed": len(unmapped_raw),
            "sum_total_count": expected_total,
            "currency": account.get("currency"),
            "pagination_truncated": False,
        }
        logger.warning("Voximplant free integrity %s", integrity)
        warnings = [
            f"slices={len(slices)}",
            f"fetched_raw={len(all_items)} mapped={len(mapped)}",
            f"sum_total_count={expected_total}",
            f"currency={account.get('currency')}",
        ]
        if expected_total and len(mapped) < expected_total:
            warning = (
                f"Voximplant free incomplete: unique_keys={len(mapped)} "
                f"< sum(total_count)={expected_total}"
            )
            logger.warning(warning)
            warnings.append(warning)
            integrity["incomplete"] = True

        return SyncResult(
            fetched=len(all_items),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
            warnings=warnings,
            extra_stats={"integrity": integrity},
        )

    async def sync_purchased_numbers(
        self, connection: ConnectionConfig, **kwargs: Any
    ) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider=self.code.value,
                    capability="purchased_numbers",
                    message="Voximplant purchased inventory out of scope v1",
                    doc_refs=contract.DOC_REFS_FREE,
                )
            ]
        )
