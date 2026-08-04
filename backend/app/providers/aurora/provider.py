"""Aurora Telecom CSV orchestrator. Docs: aurora-contract.md — read-only."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.enums import ProviderCode
from app.providers.aurora import contract, mapper, parser
from app.providers.aurora.client import AuroraClient
from app.providers.base import AbstractProvider
from app.providers.dto.common import (
    ConnectionConfig,
    DiagnosticsResult,
    RawHttpResult,
    SyncLimitation,
    SyncResult,
)
from app.providers.errors import ProviderParseError


class AuroraProvider(AbstractProvider):
    code = ProviderCode.aurora

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET all_free.csv",
                "doc_refs": contract.DOC_REFS,
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
                "action": "GET all_free.csv head (parse first row)",
            },
        }

    def _client(self, connection: ConnectionConfig) -> AuroraClient:
        return AuroraClient(connection)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = self._client(connection)
        try:
            raw, probe = await client.probe()
            if raw.status_code >= 400:
                return DiagnosticsResult(
                    ok=False,
                    message=f"Aurora HTTP {raw.status_code}",
                    checked_at=datetime.now(UTC),
                    details=probe,
                    raw=raw,
                )
            sample, meta = parser.parse_probe_bytes(
                client.raw_bytes(raw),
                truncated=bool((raw.body_json or {}).get("truncated")),
            )
            if not sample:
                return DiagnosticsResult(
                    ok=False,
                    message="Aurora CSV head has no parseable free-number row",
                    checked_at=datetime.now(UTC),
                    details={**probe, **meta},
                    raw=raw,
                )
            return DiagnosticsResult(
                ok=True,
                message=(
                    f"Aurora CSV OK (encoding={meta.get('encoding')}, "
                    f"sample={sample.msisdn})"
                ),
                checked_at=datetime.now(UTC),
                details={**probe, **meta},
                raw=raw,
            )
        except Exception as exc:  # noqa: BLE001 — surface probe failure to UI
            return DiagnosticsResult(
                ok=False,
                message=str(exc),
                checked_at=datetime.now(UTC),
                details={
                    "url": (connection.base_url or "").strip() or contract.DEFAULT_CSV_URL
                },
            )

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider=self.code.value,
                    capability="dictionaries",
                    message="Aurora free CSV has no regions/cities dictionary endpoints",
                    doc_refs=contract.DOC_REFS,
                )
            ]
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return await self.sync_regions(connection, **kwargs)

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        from app.providers.progress_emit import emit_progress

        client = self._client(connection)
        on_progress = kwargs.get("on_progress")
        await emit_progress(on_progress, "Aurora: скачивание CSV…", 0, None)
        raw = await client.fetch_csv()
        await emit_progress(on_progress, "Aurora: разбор CSV…", 0, None)
        try:
            parsed_items, unmapped_raw, meta = parser.parse_free_csv(
                raw, raw_bytes=client.raw_bytes(raw)
            )
        except ProviderParseError:
            raise
        mapped = []
        for item in parsed_items:
            mapped_item = mapper.map_number(item)
            if mapped_item:
                mapped.append(mapped_item)
            else:
                unmapped_raw.append(item.raw_payload)
        await emit_progress(
            on_progress,
            f"Aurora: разобрано {len(mapped)} (encoding={meta.get('encoding')})",
            len(mapped),
            meta.get("row_count"),
        )
        # Keep a compact envelope meta only (avoid holding full multi-MB latin-1 body)
        envelope = RawHttpResult(
            status_code=raw.status_code,
            body_text="",
            body_json={
                "bytes_len": (raw.body_json or {}).get("bytes_len"),
                "encoding": meta.get("encoding"),
                "row_count": meta.get("row_count"),
            },
            headers={},
            elapsed_ms=raw.elapsed_ms,
            request_url=raw.request_url,
        )
        return SyncResult(
            fetched=int(meta.get("row_count") or 0),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=[envelope],
            warnings=[
                f"encoding={meta.get('encoding')}",
                f"unmapped={len(unmapped_raw)}",
            ],
        )

    async def sync_purchased_numbers(
        self, connection: ConnectionConfig, **kwargs: Any
    ) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider=self.code.value,
                    capability="purchased_numbers",
                    message="Aurora provides free CSV only; no purchased export",
                    doc_refs=contract.DOC_REFS,
                )
            ]
        )
