"""Exolve orchestrator. Docs: docs/providers/exolve-contract.md."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.models.enums import InventoryKind, ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncLimitation, SyncResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.exolve import contract, mapper, parser
from app.providers.exolve.client import ExolveClient
from app.providers.progress_emit import emit_progress

logger = logging.getLogger(__name__)


class ExolveProvider(AbstractProvider):
    code = ProviderCode.exolve

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "POST /number/v1/GetFree (type×region)",
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
                "actions": ["POST /number/reference/v1/GetList"],
                "doc_refs": contract.DOC_REFS_REFERENCE,
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "POST /number/reference/v1/GetList",
            },
        }

    def _client(self, connection: ConnectionConfig) -> ExolveClient:
        return ExolveClient(connection)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = self._client(connection)
        data, raw = await client.get_reference()
        regions = data.get("regions") if isinstance(data.get("regions"), list) else []
        return DiagnosticsResult(
            ok=True,
            message=f"Exolve GetList OK (regions={len(regions)})",
            checked_at=datetime.now(timezone.utc),
            details={
                "regions": len(regions),
                "types": len(data.get("types") or [])
                if isinstance(data.get("types"), list)
                else 0,
                "categories": len(data.get("categories") or [])
                if isinstance(data.get("categories"), list)
                else 0,
            },
            raw=raw,
        )

    async def _fetch_reference(
        self, connection: ConnectionConfig, **kwargs: Any
    ) -> tuple[list, list, list[dict[str, Any]], list]:
        on_progress = kwargs.get("on_progress")
        await emit_progress(on_progress, "Exolve: справочник GetList…")
        client = self._client(connection)
        data, envelope = await client.get_reference()
        regions, cities, categories = parser.parse_reference(data)
        if not regions:
            raise ProviderError(
                "Exolve GetList returned zero regions",
                code="EXOLVE_EMPTY_REGIONS",
            )
        await emit_progress(
            on_progress,
            f"Exolve: regions={len(regions)}, cities={len(cities)}, categories={len(categories)}",
            len(regions),
            len(regions),
        )
        return regions, cities, categories, [envelope]

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        regions, cities, categories, envelopes = await self._fetch_reference(
            connection, **kwargs
        )
        return SyncResult(
            fetched=len(regions),
            parsed=len(regions),
            items={
                "regions": regions,
                "cities": cities,
                "categories": mapper.category_raw_rows(categories),
            },
            raw_envelopes=envelopes,
            warnings=[
                f"regions={len(regions)} (ALL from GetList)",
                f"cities_leaves={len(cities)}",
                f"categories={len(categories)}",
            ],
            extra_stats={
                "integrity": {
                    "regions_in_reference": len(regions),
                    "cities_leaves": len(cities),
                    "categories": len(categories),
                }
            },
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # Service for non-sipout calls sync_regions then sync_cities; avoid double fetch
        # by returning cities from a fresh GetList (cheap vs free sync).
        regions, cities, categories, envelopes = await self._fetch_reference(
            connection, **kwargs
        )
        return SyncResult(
            fetched=len(cities),
            parsed=len(cities),
            items={
                "regions": regions,
                "cities": cities,
                "categories": mapper.category_raw_rows(categories),
            },
            raw_envelopes=envelopes,
        )

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        on_progress = kwargs.get("on_progress")
        city_lookup: dict[str, tuple] = kwargs.get("city_lookup") or {}
        client = self._client(connection)

        await emit_progress(on_progress, "Exolve: справочник для списка регионов…")
        data, ref_env = await client.get_reference()
        regions, _cities, _cats = parser.parse_reference(data)
        region_ids = sorted(
            {
                int(r.region_external_id)
                for r in regions
                if r.region_external_id and str(r.region_external_id).isdigit()
            }
        )
        if not region_ids:
            raise ProviderError(
                "Exolve free sync: no region_ids from GetList",
                code="EXOLVE_EMPTY_REGIONS",
            )

        slices: list[tuple[int, int, str]] = []
        for type_id in contract.SYNC_TYPE_IDS:
            label = contract.TYPE_NAMES.get(type_id, str(type_id))
            if type_id == contract.TYPE_KDU:
                slices.append((type_id, contract.RUSSIA_REGION_ID, label))
            else:
                for rid in region_ids:
                    slices.append((type_id, rid, label))

        all_items: list[dict[str, Any]] = []
        envelopes = [ref_env]
        slices_empty = 0
        slices_failed = 0
        per_type: dict[str, int] = {n: 0 for n in contract.TYPE_NAMES.values()}

        for idx, (type_id, region_id, label) in enumerate(slices, start=1):
            await emit_progress(
                on_progress,
                f"Exolve slice {idx}/{len(slices)} {label} region={region_id}",
                len(all_items),
                None,
            )
            try:
                page_items, envs = await client.iter_free_slice(
                    type_id=type_id,
                    region_id=region_id,
                    on_progress=on_progress,
                    type_label=label,
                )
                envelopes.extend(envs)
                if not page_items:
                    slices_empty += 1
                else:
                    for it in page_items:
                        it = dict(it)
                        it["_exolve_region_id"] = region_id
                        it["_exolve_type_id"] = type_id
                        all_items.append(it)
                    per_type[label] = per_type.get(label, 0) + len(page_items)
            except (ProviderAuthError, ProviderError, ProviderTransportError):
                raise
            except Exception as exc:
                slices_failed += 1
                logger.exception(
                    "Exolve free slice failed type=%s region=%s", type_id, region_id
                )
                raise ProviderError(
                    f"Exolve free slice failed type={type_id} region={region_id}: {exc}",
                    code="EXOLVE_SLICE_FAILED",
                    details={"type_id": type_id, "region_id": region_id},
                ) from exc

        await emit_progress(
            on_progress, "Exolve: разбор и маппинг…", len(all_items), len(all_items)
        )
        mapped = []
        unmapped_raw: list[dict] = []
        for raw in all_items:
            region_id = raw.get("_exolve_region_id")
            parsed = parser.parse_number_item(
                raw, region_id=int(region_id) if region_id is not None else None
            )
            num = mapper.map_number(
                parsed, inventory_kind=InventoryKind.free, city_lookup=city_lookup
            )
            if num:
                mapped.append(num)
            else:
                unmapped_raw.append(raw)

        integrity = {
            "regions_in_reference": len(region_ids),
            "slices_planned": len(slices),
            "slices_done": len(slices) - slices_failed,
            "slices_empty": slices_empty,
            "slices_failed": slices_failed,
            "fetched_raw": len(all_items),
            "unique_keys": len({m.provider_number_key for m in mapped}),
            "map_failed": len(unmapped_raw),
            "per_type_counts": per_type,
            "pagination_truncated": False,
        }
        logger.warning("Exolve free integrity %s", integrity)
        return SyncResult(
            fetched=len(all_items),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
            warnings=[
                f"slices={len(slices)} empty={slices_empty}",
                f"fetched_raw={len(all_items)} mapped={len(mapped)}",
                f"per_type={per_type}",
            ],
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
                    message="Exolve purchased inventory out of scope for v1",
                    doc_refs=contract.DOC_REFS_FREE,
                )
            ]
        )
