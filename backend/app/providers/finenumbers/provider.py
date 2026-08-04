"""Finenumbers PSTN provider orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.enums import ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncLimitation, SyncResult
from app.providers.finenumbers import contract, mapper
from app.providers.finenumbers.client import FinenumbersClient


class FinenumbersProvider(AbstractProvider):
    code = ProviderCode.finenumbers

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "lookup/by-inn expand ranges",
            },
            "purchased_numbers": {
                "supported": False,
                "source": "missing",
                "action": None,
            },
            "dictionaries": {
                "supported": False,
                "source": "missing",
                "action": None,
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "lookup/by-inn page=1",
            },
            "operator_enrichment": {
                "supported": True,
                "source": "documentation_verified",
                "action": "lookup?phone= + range cache",
            },
        }

    def _client(self, connection: ConnectionConfig) -> FinenumbersClient:
        return FinenumbersClient(connection)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = self._client(connection)
        raw = await client.lookup_by_inn(page=1, page_size=1)
        ok = raw.status_code < 400 and isinstance(raw.body_json, dict)
        meta = (raw.body_json or {}).get("meta") if ok else {}
        return DiagnosticsResult(
            ok=ok,
            message=(
                f"Finenumbers by-inn OK, totalRows={meta.get('totalRows')}"
                if ok
                else f"Finenumbers by-inn failed HTTP {raw.status_code}"
            ),
            checked_at=datetime.now(timezone.utc),
            details={"inn": contract.OPERATOR_INN, "action": "lookup/by-inn"},
            raw=raw,
        )

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider=self.code.value,
                    capability="dictionaries",
                    message="Finenumbers PSTN has no regions dictionary endpoint",
                )
            ]
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return await self.sync_regions(connection, **kwargs)

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        from app.providers.errors import ProviderError
        from app.providers.progress_emit import emit_progress

        on_progress = kwargs.get("on_progress")
        client = self._client(connection)
        ranges, envelopes = await client.iter_all_ranges_by_inn(on_progress=on_progress)
        await emit_progress(
            on_progress, f"Finenumbers: раскрытие диапазонов… ({len(ranges)})"
        )
        numbers = mapper.expand_ranges(ranges)
        await emit_progress(
            on_progress,
            f"Finenumbers: раскрыто {len(numbers)}",
            len(numbers),
            len(numbers),
        )
        if len(numbers) > contract.MAX_EXPAND_NUMBERS:
            raise ProviderError(
                (
                    f"Finenumbers expand too large: {len(numbers)} numbers "
                    f"(max {contract.MAX_EXPAND_NUMBERS})"
                ),
                code="PROVIDER_EXPAND_LIMIT",
                details={
                    "expanded": len(numbers),
                    "max": contract.MAX_EXPAND_NUMBERS,
                    "ranges": len(ranges),
                },
            )
        mapped = [n for n in numbers if n.provider_number_key]
        unmapped_raw = [
            n.raw_payload for n in numbers if not n.provider_number_key and n.raw_payload
        ]
        return SyncResult(
            fetched=len(ranges),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
            warnings=[f"Expanded {len(ranges)} ranges into {len(mapped)} numbers"],
        )

    async def sync_purchased_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider=self.code.value,
                    capability="purchased_numbers",
                    message="Finenumbers PSTN provider loads free inventory only (by-inn ranges)",
                )
            ]
        )
