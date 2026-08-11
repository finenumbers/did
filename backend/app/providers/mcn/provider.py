"""MCN Telecom orchestrator. Docs: docs/providers/mcn-contract.md."""

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
from app.providers.dto.geo import ParsedRegion
from app.providers.mcn import contract, mapper, parser
from app.providers.mcn.client import McnClient

logger = logging.getLogger(__name__)


class McnProvider(AbstractProvider):
    code = ProviderCode.mcn

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET /api/protected/showcase/numbers (RU, all pages/cities)",
                "doc_refs": contract.DOC_REFS_VITRINA,
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
                    "GET /api/protected/showcase/countries",
                    "GET /api/protected/showcase/regions",
                    "GET /api/protected/showcase/cities",
                ],
                "doc_refs": contract.DOC_REFS_VITRINA,
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET /api/protected/showcase/countries (auth canary)",
                "doc_refs": contract.DOC_REFS_TOKEN,
            },
        }

    def _client(self, connection: ConnectionConfig, **kwargs: Any) -> McnClient:
        return McnClient(connection, **kwargs)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = self._client(connection)
        mode, raw = await client.probe_auth_mode()
        # Persist chosen mode back into connection auth for callers that save cfg
        connection.auth_settings = dict(connection.auth_settings or {})
        connection.auth_settings[contract.AUTH_HEADER_MODE] = mode
        ok_ru = parser.has_ru_country(raw.body_json)
        if not ok_ru:
            return DiagnosticsResult(
                ok=False,
                message="MCN countries OK but RU (643) not found",
                checked_at=datetime.now(timezone.utc),
                details={"auth_header_mode": mode, "has_ru": False},
                raw=raw,
            )
        return DiagnosticsResult(
            ok=True,
            message="MCN OK",
            checked_at=datetime.now(timezone.utc),
            details={"auth_header_mode": mode, "has_ru": True},
            raw=raw,
        )

    async def _load_dictionaries(
        self, connection: ConnectionConfig, **kwargs: Any
    ) -> tuple[list, list, list, dict[str, Any]]:
        on_progress = kwargs.get("on_progress")
        client = self._client(connection)
        # Ensure auth mode
        if not (connection.auth_settings or {}).get(contract.AUTH_HEADER_MODE):
            mode, _ = await client.probe_auth_mode()
            connection.auth_settings = dict(connection.auth_settings or {})
            connection.auth_settings[contract.AUTH_HEADER_MODE] = mode
            client.auth_header_mode = mode

        await emit_progress(on_progress, "MCN: countries")
        countries_body, env_c = await client.get_countries()
        if not parser.has_ru_country(countries_body):
            raise ProviderError(
                "MCN: RU countryCode=643 missing from showcase/countries",
                code="MCN_NO_RU",
            )
        await emit_progress(on_progress, "MCN: regions")
        regions_body, env_r = await client.get_regions()
        regions = parser.parse_regions(regions_body)
        await emit_progress(on_progress, "MCN: cities RU")
        cities_body, env_cities = await client.get_cities()
        cities = parser.parse_cities(cities_body)
        if not cities:
            raise ProviderError(
                "MCN: zero cities for countryCode=643",
                code="MCN_EMPTY_CITIES",
            )
        # Prefer region rows from regions API; supplement from city.region
        if not regions:
            seen: set[str] = set()
            for c in cities:
                if c.region_external_id and c.region_external_id not in seen:
                    seen.add(c.region_external_id)
                    regions.append(
                        ParsedRegion(
                            raw_payload={
                                "id": c.region_external_id,
                                "name": c.region_name,
                            },
                            region_external_id=c.region_external_id,
                            name=c.region_name,
                        )
                    )
        cities_raw = (
            parser.extract_list_payload(cities_body)
            if not isinstance(cities_body, list)
            else cities_body
        )
        if isinstance(cities_body, dict) and isinstance(cities_body.get("cities"), list):
            cities_raw = cities_body["cities"]
        meta = {
            "cities_raw": [r for r in cities_raw if isinstance(r, dict)],
            "auth_header_mode": client.auth_header_mode,
        }
        envelopes = [env_c, env_r, env_cities]
        return regions, cities, envelopes, meta

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        regions, cities, envelopes, meta = await self._load_dictionaries(
            connection, **kwargs
        )
        return SyncResult(
            fetched=len(regions),
            parsed=len(regions),
            items={"regions": regions, "cities": cities},
            raw_envelopes=envelopes,
            warnings=[
                f"regions={len(regions)}",
                f"cities={len(cities)}",
                f"auth_mode={meta.get('auth_header_mode')}",
            ],
            extra_stats={
                "integrity": {
                    "regions": len(regions),
                    "cities": len(cities),
                },
                "_mcn_cities_raw": meta.get("cities_raw") or [],
            },
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return await self.sync_regions(connection, **kwargs)

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        on_progress = kwargs.get("on_progress")
        city_lookup: dict[str, tuple] = kwargs.get("city_lookup") or {}
        client = self._client(connection)

        if not (connection.auth_settings or {}).get(contract.AUTH_HEADER_MODE):
            mode, _ = await client.probe_auth_mode()
            connection.auth_settings = dict(connection.auth_settings or {})
            connection.auth_settings[contract.AUTH_HEADER_MODE] = mode
            client.auth_header_mode = mode

        await emit_progress(on_progress, "MCN: probe page size")
        page_limit = await client.probe_page_limit()
        await emit_progress(on_progress, f"MCN: limitPerPage={page_limit}")

        await emit_progress(on_progress, "MCN: cities for free plan")
        cities_body, env_cities = await client.get_cities()
        cities_raw = parser.extract_list_payload(cities_body)
        if isinstance(cities_body, dict) and isinstance(cities_body.get("cities"), list):
            cities_raw = cities_body["cities"]
        stock_cities = mapper.city_free_counts(
            [r for r in cities_raw if isinstance(r, dict)]
        )

        # Country-wide first page for totalNumbers
        country_items, country_total, env0 = await client.get_numbers_page(
            page_number=1, limit_per_page=page_limit
        )
        envelopes = [env_cities, env0]
        use_city_fanout = False
        if country_total is None:
            use_city_fanout = True
        elif stock_cities and country_total > 0:
            # If first page empty but cities claim stock → fan-out
            if not country_items and country_total > 0:
                use_city_fanout = True

        all_items: list[dict[str, Any]] = []
        slice_metas: list[dict[str, Any]] = []

        if not use_city_fanout:
            await emit_progress(
                on_progress,
                f"MCN free country-wide totalNumbers={country_total}",
            )
            # Restart full country pagination (include first page)
            items, envs, meta = await client.iter_numbers_slice(
                city_id=None,
                expected_count=country_total,
                on_progress=on_progress,
                label="RU",
            )
            # iter starts from page 1 again — fine
            all_items.extend(items)
            envelopes.extend(envs)
            slice_metas.append(meta)
        else:
            if not stock_cities:
                # Fallback: still try country-wide even without counts
                items, envs, meta = await client.iter_numbers_slice(
                    on_progress=on_progress, label="RU"
                )
                all_items.extend(items)
                envelopes.extend(envs)
                slice_metas.append(meta)
            else:
                await emit_progress(
                    on_progress,
                    f"MCN free city fan-out cities={len(stock_cities)}",
                    0,
                    len(stock_cities),
                )
                sem = asyncio.Semaphore(contract.MAX_SLICE_CONCURRENCY)
                lock = asyncio.Lock()
                done = 0

                async def _one(row: tuple[int, int, str | None, str | None]) -> None:
                    nonlocal done
                    city_id, free_cnt, city_name, region_name = row
                    async with sem:
                        items, envs, meta = await client.iter_numbers_slice(
                            city_id=city_id,
                            expected_count=free_cnt,
                            on_progress=on_progress,
                            label=f"city={city_id}",
                        )
                    for it in items:
                        it = dict(it)
                        it["_mcn_city_name"] = city_name
                        it["_mcn_region_name"] = region_name
                        async with lock:
                            all_items.append(it)
                    async with lock:
                        envelopes.extend(envs)
                        slice_metas.append(meta)
                        done += 1
                        await emit_progress(
                            on_progress,
                            f"MCN free cities done {done}/{len(stock_cities)}",
                            done,
                            len(stock_cities),
                        )

                try:
                    await asyncio.gather(*[_one(r) for r in stock_cities])
                except (ProviderAuthError, ProviderError, ProviderTransportError):
                    raise
                except Exception as exc:
                    raise ProviderError(
                        f"MCN free fan-out failed: {exc}",
                        code="MCN_FANOUT_FAILED",
                    ) from exc

        await emit_progress(
            on_progress, "MCN: разбор и маппинг", len(all_items), len(all_items)
        )
        mapped = []
        unmapped_raw: list[dict] = []
        for raw_item in all_items:
            parsed = parser.parse_number_item(
                raw_item,
                city_name=raw_item.get("_mcn_city_name"),
                region_name=raw_item.get("_mcn_region_name"),
            )
            num = mapper.map_number(
                parsed,
                inventory_kind=InventoryKind.free,
                city_lookup=city_lookup,
            )
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

        sum_totals = sum(
            int(m["total_numbers"])
            for m in slice_metas
            if m.get("total_numbers") is not None
        )
        integrity = {
            "page_limit": page_limit,
            "use_city_fanout": use_city_fanout,
            "slices": len(slice_metas),
            "fetched_raw": len(all_items),
            "unique_keys": len(mapped),
            "map_failed": len(unmapped_raw),
            "sum_total_numbers": sum_totals,
            "country_total_hint": country_total,
            "auth_header_mode": client.auth_header_mode,
        }
        logger.warning("MCN free integrity %s", integrity)

        if sum_totals and len(all_items) < sum_totals:
            raise ProviderError(
                (
                    f"MCN free incomplete: fetched_raw={len(all_items)} "
                    f"< sum(totalNumbers)={sum_totals}"
                ),
                code="MCN_FREE_INCOMPLETE",
                details=integrity,
            )

        return SyncResult(
            fetched=len(all_items),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
            warnings=[
                f"fanout={use_city_fanout}",
                f"fetched_raw={len(all_items)} mapped={len(mapped)}",
                f"sum_total_numbers={sum_totals}",
                f"limitPerPage={page_limit}",
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
                    message="MCN purchased inventory out of scope v1",
                    doc_refs=contract.DOC_REFS_VITRINA,
                )
            ]
        )
