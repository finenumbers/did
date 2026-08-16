"""Finenumbers PSTN + REG provider orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.enums import ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncLimitation, SyncResult
from app.providers.dto.numbers import NormalizedNumber
from app.providers.finenumbers import contract, mapper
from app.providers.finenumbers.client import FinenumbersClient
from app.providers.finenumbers.reg_client import FinenumbersRegClient
from app.providers.finenumbers.reg_mapper import map_reg_endpoints, reg_key_set


class FinenumbersProvider(AbstractProvider):
    code = ProviderCode.finenumbers

    def __init__(self) -> None:
        super().__init__()
        self._reg_numbers: list[NormalizedNumber] | None = None
        self._reg_keys: set[str] | None = None
        self._reg_envelopes: list[Any] | None = None
        self._reg_unmapped: list[dict[str, Any]] | None = None

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "lookup/by-inn expand ranges minus REG",
            },
            "purchased_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "REG GET /api/phones endpoints",
            },
            "dictionaries": {
                "supported": False,
                "source": "missing",
                "action": None,
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "lookup/by-inn page=1 (+ REG phones if reg_key)",
            },
            "operator_enrichment": {
                "supported": True,
                "source": "documentation_verified",
                "action": "lookup?phone= + range cache",
            },
        }

    def _client(self, connection: ConnectionConfig) -> FinenumbersClient:
        return FinenumbersClient(connection)

    def _reg_client(self, connection: ConnectionConfig) -> FinenumbersRegClient:
        return FinenumbersRegClient(connection)

    async def _ensure_reg_loaded(
        self, connection: ConnectionConfig, *, on_progress: Any | None = None
    ) -> None:
        if self._reg_numbers is not None and self._reg_keys is not None:
            return
        client = self._reg_client(connection)
        try:
            rows, envelopes = await client.iter_all_endpoint_numbers(on_progress=on_progress)
        finally:
            await client.aclose()
        mapped, unmapped = map_reg_endpoints(rows)
        for num in mapped:
            num.rtu_connected = contract.RTU_CONNECTED
        self._reg_numbers = mapped
        self._reg_keys = reg_key_set(mapped)
        self._reg_envelopes = envelopes
        self._reg_unmapped = unmapped

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = self._client(connection)
        try:
            raw = await client.lookup_by_inn(page=1, page_size=1)
        finally:
            await client.aclose()
        ok = raw.status_code < 400 and isinstance(raw.body_json, dict)
        meta = (raw.body_json or {}).get("meta") if ok else {}
        details: dict[str, Any] = {"inn": contract.OPERATOR_INN, "action": "lookup/by-inn"}
        message = (
            f"Finenumbers by-inn OK, totalRows={meta.get('totalRows')}"
            if ok
            else f"Finenumbers by-inn failed HTTP {raw.status_code}"
        )
        if connection.auth_settings.get(contract.REG_AUTH_SETTINGS_KEY):
            reg = self._reg_client(connection)
            try:
                reg_raw = await reg.list_phones_page(
                    kind="endpoints_registered", page=1, page_size=1
                )
            finally:
                await reg.aclose()
            reg_ok = reg_raw.status_code < 400
            details["reg"] = {
                "ok": reg_ok,
                "status_code": reg_raw.status_code,
                "action": "GET /api/phones",
            }
            if not reg_ok:
                ok = False
                message = f"{message}; REG phones HTTP {reg_raw.status_code}"
            else:
                message = f"{message}; REG phones OK"
        return DiagnosticsResult(
            ok=ok,
            message=message,
            checked_at=datetime.now(timezone.utc),
            details=details,
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
        from app.providers.finenumbers.reg_mapper import catalog_match_key
        from app.providers.progress_emit import emit_progress

        on_progress = kwargs.get("on_progress")
        await self._ensure_reg_loaded(connection, on_progress=on_progress)
        reg_keys = self._reg_keys or set()

        client = self._client(connection)
        try:
            ranges, envelopes = await client.iter_all_ranges_by_inn(on_progress=on_progress)
        finally:
            await client.aclose()
        await emit_progress(
            on_progress, f"Finenumbers: раскрытие диапазонов ({len(ranges)})"
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
        free_kept: list[NormalizedNumber] = []
        excluded = 0
        for n in numbers:
            if not n.provider_number_key:
                continue
            key = catalog_match_key(n.abc_code, n.number_local, n.msisdn)
            if key and key in reg_keys:
                excluded += 1
                continue
            free_kept.append(n)
        unmapped_raw = [
            n.raw_payload for n in numbers if not n.provider_number_key and n.raw_payload
        ]
        return SyncResult(
            fetched=len(ranges),
            parsed=len(free_kept),
            items=free_kept,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
            warnings=[
                f"Expanded {len(ranges)} ranges into {len(numbers)} numbers; "
                f"excluded {excluded} present in REG → free={len(free_kept)}"
            ],
            extra_stats={
                "reg_keys": len(reg_keys),
                "excluded_to_purchased": excluded,
            },
        )

    async def sync_purchased_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        on_progress = kwargs.get("on_progress")
        await self._ensure_reg_loaded(connection, on_progress=on_progress)
        mapped = list(self._reg_numbers or [])
        return SyncResult(
            fetched=len(mapped),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=list(self._reg_unmapped or []),
            raw_envelopes=list(self._reg_envelopes or []),
            warnings=[f"REG endpoints mapped to {len(mapped)} purchased numbers"],
            extra_stats={"reg_keys": len(self._reg_keys or ())},
        )
