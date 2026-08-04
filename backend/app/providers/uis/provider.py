"""UIS Data API orchestrator. Docs: uis-contract.md — read-only."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.enums import InventoryKind, ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import (
    ConnectionConfig,
    DiagnosticsResult,
    SyncLimitation,
    SyncResult,
)
from app.providers.uis import contract, mapper, parser
from app.providers.uis.client import UisClient


class UisProvider(AbstractProvider):
    code = ProviderCode.uis

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS,
            },
            "purchased_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": contract.METHOD_VIRTUAL_NUMBERS,
            },
            "dictionaries": {
                "supported": False,
                "source": "missing",
                "action": None,
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": contract.METHOD_VIRTUAL_NUMBERS,
            },
        }

    def _client(self, connection: ConnectionConfig) -> UisClient:
        return UisClient(connection)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = self._client(connection)
        try:
            client.require_access_token()
            raw = await client.get_page(contract.METHOD_VIRTUAL_NUMBERS, offset=0, limit=1)
            parser.parse_list_page(raw)
            return DiagnosticsResult(
                ok=True,
                message="UIS get.virtual_numbers (limit=1) OK",
                checked_at=datetime.now(UTC),
                details={"method": contract.METHOD_VIRTUAL_NUMBERS},
                raw=raw,
            )
        except Exception as exc:  # noqa: BLE001 — surface any probe failure to UI
            return DiagnosticsResult(
                ok=False,
                message=str(exc),
                checked_at=datetime.now(UTC),
                details={"method": contract.METHOD_VIRTUAL_NUMBERS},
            )

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider=self.code.value,
                    capability="dictionaries",
                    message="UIS Data API has no regions/cities dictionary endpoints",
                    doc_refs=["docs/providers/uis-contract.md"],
                )
            ]
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return await self.sync_regions(connection, **kwargs)

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        client = self._client(connection)
        on_progress = kwargs.get("on_progress")
        items, envelopes = await client.iter_all(
            contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS,
            on_progress=on_progress,
        )
        mapped = []
        unmapped_raw: list[dict] = []
        for item in items:
            parsed = parser.parse_available_item(item)
            mapped_item = mapper.map_number(parsed, inventory_kind=InventoryKind.free)
            if mapped_item:
                mapped.append(mapped_item)
            else:
                unmapped_raw.append(item)
        return SyncResult(
            fetched=len(items),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
        )

    async def sync_purchased_numbers(
        self, connection: ConnectionConfig, **kwargs: Any
    ) -> SyncResult:
        client = self._client(connection)
        on_progress = kwargs.get("on_progress")
        items, envelopes = await client.iter_all(
            contract.METHOD_VIRTUAL_NUMBERS,
            on_progress=on_progress,
        )
        mapped = []
        unmapped_raw: list[dict] = []
        for item in items:
            parsed = parser.parse_virtual_item(item)
            mapped_item = mapper.map_number(parsed, inventory_kind=InventoryKind.purchased)
            if mapped_item:
                mapped.append(mapped_item)
            else:
                unmapped_raw.append(item)
        return SyncResult(
            fetched=len(items),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
        )
