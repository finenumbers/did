"""Exolve orchestrator. Docs: docs/providers/exolve-contract.md."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.models.enums import InventoryKind, ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import (
    ConnectionConfig,
    DiagnosticsResult,
    RawHttpResult,
    SyncLimitation,
    SyncResult,
)
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.exolve import contract, mapper, parser
from app.providers.exolve.client import ExolveClient
from app.providers.progress_emit import emit_progress

logger = logging.getLogger(__name__)


def _category_ids_by_type(categories: list[dict[str, Any]]) -> dict[int, list[int]]:
    """Map type_id → category_ids from GetList; fall back to docs table per type."""
    by_type: dict[int, list[int]] = {tid: [] for tid in contract.SYNC_TYPE_IDS}
    for row in categories:
        if not isinstance(row, dict):
            continue
        try:
            tid = int(row.get("type_id"))
            cid = int(row.get("category_id"))
        except (TypeError, ValueError):
            continue
        if tid in by_type and cid not in by_type[tid]:
            by_type[tid].append(cid)
    for tid in contract.SYNC_TYPE_IDS:
        if not by_type[tid]:
            by_type[tid] = list(contract.DOC_CATEGORY_IDS_BY_TYPE.get(tid, ()))
        else:
            by_type[tid].sort()
    return by_type


def _build_free_slices(
    *,
    region_ids: list[int],
    sync_mode: str,
    categories_raw: list[dict[str, Any]],
) -> list[tuple[int, int, int | None, str]]:
    """Return (type_id, region_id, category_id|None, label)."""
    slices: list[tuple[int, int, int | None, str]] = []
    cats_by_type = _category_ids_by_type(categories_raw)
    use_category = sync_mode == contract.SYNC_MODE_TYPE_REGION_CATEGORY

    for type_id in contract.SYNC_TYPE_IDS:
        label = contract.TYPE_NAMES.get(type_id, str(type_id))
        regions = (
            [contract.RUSSIA_REGION_ID]
            if type_id == contract.TYPE_KDU
            else region_ids
        )
        cat_ids: list[int | None]
        if use_category:
            cat_ids = list(cats_by_type.get(type_id) or [])
            if not cat_ids:
                cat_ids = [None]
        else:
            cat_ids = [None]
        for rid in regions:
            for cid in cat_ids:
                slices.append((type_id, rid, cid, label))
    return slices


class ExolveProvider(AbstractProvider):
    code = ProviderCode.exolve

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "POST /number/v1/GetFree (type×region or type×region×category)",
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
                "action": "POST GetList + GetFree canary probes",
            },
        }

    def _client(self, connection: ConnectionConfig, **kwargs: Any) -> ExolveClient:
        return ExolveClient(connection, **kwargs)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = self._client(connection)
        data, raw = await client.get_reference()
        regions = data.get("regions") if isinstance(data.get("regions"), list) else []
        probes = await client.probe_get_free()
        totals = client.probe_number_totals(probes)
        chosen_random = client.choose_random_mode_from_probes(probes)
        sync_mode = client.choose_sync_mode_from_probes(probes)
        message = (
            f"Exolve GetList OK (regions={len(regions)}); "
            f"GetFree doc_example_numbers={totals['doc_example_numbers']} "
            f"no_category_numbers={totals['no_category_numbers']} "
            f"sync_mode={sync_mode} random_mode={chosen_random}"
        )
        if totals["best_numbers"] == 0:
            message += (
                " — GetFree empty including docs examples "
                "(category_id+random:true); check app inventory/balance in Exolve LK"
            )
        elif sync_mode == contract.SYNC_MODE_TYPE_REGION_CATEGORY:
            message += " — docs examples need category_id; sync will use type×region×category"
        return DiagnosticsResult(
            ok=True,
            message=message,
            checked_at=datetime.now(timezone.utc),
            details={
                "regions": len(regions),
                "types": len(data.get("types") or [])
                if isinstance(data.get("types"), list)
                else 0,
                "categories": len(data.get("categories") or [])
                if isinstance(data.get("categories"), list)
                else 0,
                "get_free_probes": probes,
                "get_free_best_numbers": totals["best_numbers"],
                "doc_example_numbers": totals["doc_example_numbers"],
                "no_category_numbers": totals["no_category_numbers"],
                "recommended_random_mode": chosen_random,
                "recommended_sync_mode": sync_mode,
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

        await emit_progress(on_progress, "Exolve: GetFree canary…")
        probe_client = self._client(connection)
        probes = await probe_client.probe_get_free()
        totals = probe_client.probe_number_totals(probes)
        random_mode = probe_client.choose_random_mode_from_probes(probes)
        sync_mode = probe_client.choose_sync_mode_from_probes(probes)
        logger.warning(
            "Exolve GetFree canary probes=%s sync_mode=%s random_mode=%s totals=%s",
            probes,
            sync_mode,
            random_mode,
            totals,
        )
        await emit_progress(
            on_progress,
            (
                f"Exolve canary doc={totals['doc_example_numbers']} "
                f"no_cat={totals['no_category_numbers']} "
                f"sync_mode={sync_mode} random_mode={random_mode}"
            ),
        )

        client = self._client(connection, random_mode=random_mode)

        await emit_progress(on_progress, "Exolve: справочник для списка регионов…")
        data, ref_env = await client.get_reference()
        regions, _cities, categories_raw = parser.parse_reference(data)
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

        slices = _build_free_slices(
            region_ids=region_ids,
            sync_mode=sync_mode,
            categories_raw=categories_raw,
        )

        all_items: list[dict[str, Any]] = []
        envelopes = [ref_env]
        slices_empty = 0
        slices_failed = 0
        per_type: dict[str, int] = {n: 0 for n in contract.TYPE_NAMES.values()}
        first_response_diag: dict[str, Any] | None = None

        def _on_first_raw(raw: RawHttpResult) -> None:
            nonlocal first_response_diag
            if first_response_diag is not None:
                return
            first_response_diag = parser.summarize_free_payload(
                raw.status_code, raw.body_json, raw.body_text or ""
            )
            logger.warning("Exolve GetFree first sync response %s", first_response_diag)

        for idx, (type_id, region_id, category_id, label) in enumerate(slices, start=1):
            cat_part = f" cat={category_id}" if category_id is not None else ""
            await emit_progress(
                on_progress,
                f"Exolve slice {idx}/{len(slices)} {label} region={region_id}{cat_part}",
                len(all_items),
                None,
            )
            try:
                page_items, envs = await client.iter_free_slice(
                    type_id=type_id,
                    region_id=region_id,
                    category_id=category_id,
                    on_progress=on_progress,
                    type_label=label,
                    on_first_raw=_on_first_raw if first_response_diag is None else None,
                )
                envelopes.extend(envs)
                if not page_items:
                    slices_empty += 1
                else:
                    for it in page_items:
                        it = dict(it)
                        it["_exolve_region_id"] = region_id
                        it["_exolve_type_id"] = type_id
                        if category_id is not None:
                            it["_exolve_category_id"] = category_id
                        all_items.append(it)
                    per_type[label] = per_type.get(label, 0) + len(page_items)
            except (ProviderAuthError, ProviderError, ProviderTransportError):
                raise
            except Exception as exc:
                slices_failed += 1
                logger.exception(
                    "Exolve free slice failed type=%s region=%s category=%s",
                    type_id,
                    region_id,
                    category_id,
                )
                raise ProviderError(
                    (
                        f"Exolve free slice failed type={type_id} "
                        f"region={region_id} category={category_id}: {exc}"
                    ),
                    code="EXOLVE_SLICE_FAILED",
                    details={
                        "type_id": type_id,
                        "region_id": region_id,
                        "category_id": category_id,
                    },
                ) from exc

        await emit_progress(
            on_progress, "Exolve: разбор и маппинг…", len(all_items), len(all_items)
        )
        mapped = []
        unmapped_raw: list[dict] = []
        for raw_item in all_items:
            region_id = raw_item.get("_exolve_region_id")
            parsed = parser.parse_number_item(
                raw_item, region_id=int(region_id) if region_id is not None else None
            )
            num = mapper.map_number(
                parsed, inventory_kind=InventoryKind.free, city_lookup=city_lookup
            )
            if num:
                mapped.append(num)
            else:
                unmapped_raw.append(raw_item)

        # Dedupe by provider key (category cartesian may overlap if API ignores filter)
        seen_keys: set[str] = set()
        deduped = []
        for num in mapped:
            key = num.provider_number_key or ""
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(num)
        mapped = deduped

        integrity = {
            "regions_in_reference": len(region_ids),
            "slices_planned": len(slices),
            "slices_done": len(slices) - slices_failed,
            "slices_empty": slices_empty,
            "slices_failed": slices_failed,
            "fetched_raw": len(all_items),
            "unique_keys": len(mapped),
            "map_failed": len(unmapped_raw),
            "per_type_counts": per_type,
            "pagination_truncated": False,
            "random_mode": random_mode,
            "sync_mode": sync_mode,
            "canary_totals": totals,
            "canary_probes": probes,
            "first_response": first_response_diag,
        }
        logger.warning("Exolve free integrity %s", integrity)

        if len(all_items) == 0 and slices_empty == len(slices):
            raise ProviderError(
                (
                    f"Exolve GetFree empty ({slices_empty}/{len(slices)} slices, "
                    f"mode={sync_mode}); docs examples also empty "
                    f"(doc_example_numbers={totals['doc_example_numbers']}) — "
                    "check app inventory/balance in Exolve LK"
                ),
                code="EXOLVE_FREE_EMPTY",
                details=integrity,
            )

        return SyncResult(
            fetched=len(all_items),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
            warnings=[
                f"slices={len(slices)} empty={slices_empty} mode={sync_mode}",
                f"fetched_raw={len(all_items)} mapped={len(mapped)}",
                f"per_type={per_type}",
                f"random_mode={random_mode}",
                (
                    f"canary doc={totals['doc_example_numbers']} "
                    f"no_cat={totals['no_category_numbers']}"
                ),
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
