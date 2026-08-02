"""SipOut orchestrator. Docs: SipOut.html + sipout-contract.md."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.enums import InventoryKind, ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncResult
from app.providers.sipout.client import SipOutClient
from app.providers.sipout import mapper, parser


class SipOutProvider(AbstractProvider):
    code = ProviderCode.sipout

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "did/free_list",
            },
            "purchased_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "did/connected_list",
            },
            "dictionaries": {
                "supported": True,
                "source": "documentation_verified",
                "action": "did/get_cities",
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "balance/get",
            },
        }

    def _client(self, connection: ConnectionConfig) -> SipOutClient:
        return SipOutClient(connection)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        # VERIFIED: method=balance&action=get
        client = self._client(connection)
        raw = await client.get_balance()
        try:
            parser.parse_balance(raw)
            return DiagnosticsResult(
                ok=True,
                message="SipOut balance/get returned result=ok",
                checked_at=datetime.now(timezone.utc),
                details={"action": "balance/get"},
                raw=raw,
            )
        except Exception as exc:
            return DiagnosticsResult(
                ok=False,
                message=str(exc),
                checked_at=datetime.now(timezone.utc),
                details={"action": "balance/get"},
                raw=raw,
            )

    async def _fetch_geo(self, connection: ConnectionConfig) -> SyncResult:
        # VERIFIED: method=did&action=get_cities — fills regions and cities
        client = self._client(connection)
        raw = await client.get_cities()
        regions, cities = parser.parse_geo(raw)
        return SyncResult(
            fetched=len(regions) + len(cities),
            parsed=len(regions) + len(cities),
            items={"regions": regions, "cities": cities},
            raw_envelopes=[raw],
        )

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return await self._fetch_geo(connection)

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return await self._fetch_geo(connection)

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # VERIFIED: free_list; locked: single call, no city crawl
        client = self._client(connection)
        mask = kwargs.get("mask")
        raw = await client.free_list(mask=mask)
        parsed = parser.parse_number_list(raw)
        city_lookup: dict[str, tuple] = kwargs.get("city_lookup") or {}
        mapped = []
        for item in parsed:
            city_name = region_name = region_id = None
            if item.city_external_id and item.city_external_id in city_lookup:
                tup = city_lookup[item.city_external_id]
                city_name = tup[0] if len(tup) > 0 else None
                region_id = tup[1] if len(tup) > 1 else None
                region_name = tup[2] if len(tup) > 2 else None
            mapped_item = mapper.map_number(
                item,
                inventory_kind=InventoryKind.free,
                city_name=city_name,
                region_name=region_name,
                region_external_id=region_id,
            )
            if mapped_item:
                mapped.append(mapped_item)
        return SyncResult(
            fetched=len(parsed),
            parsed=len(mapped),
            items=mapped,
            raw_envelopes=[raw],
            warnings=["Item fields are EXAMPLE-CONFIRMED only"] if mapped else [],
        )

    async def sync_purchased_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # VERIFIED: connected_list → purchased (product decision)
        client = self._client(connection)
        raw = await client.connected_list()
        parsed = parser.parse_number_list(raw)
        city_lookup: dict[str, tuple] = kwargs.get("city_lookup") or {}
        mapped = []
        for item in parsed:
            city_name = region_name = region_id = None
            if item.city_external_id and item.city_external_id in city_lookup:
                tup = city_lookup[item.city_external_id]
                city_name = tup[0]
                region_id = tup[1] if len(tup) > 1 else None
                region_name = tup[2] if len(tup) > 2 else None
            mapped_item = mapper.map_number(
                item,
                inventory_kind=InventoryKind.purchased,
                city_name=city_name,
                region_name=region_name,
                region_external_id=region_id,
            )
            if mapped_item:
                mapped.append(mapped_item)
        return SyncResult(
            fetched=len(parsed),
            parsed=len(mapped),
            items=mapped,
            raw_envelopes=[raw],
        )
