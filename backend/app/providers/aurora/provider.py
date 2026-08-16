"""Aurora Telecom CSV orchestrator. Docs: aurora-contract.md — read-only."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


class AuroraProvider(AbstractProvider):
    code = ProviderCode.aurora

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET configured CSV URLs from Settings (extra_settings.csv_files)",
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
                "action": "GET head of first configured CSV + parse first row",
            },
        }

    def _client(self, connection: ConnectionConfig) -> AuroraClient:
        return AuroraClient(connection)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        try:
            client = self._client(connection)
        except Exception as exc:  # noqa: BLE001
            return DiagnosticsResult(
                ok=False,
                message=str(exc),
                checked_at=datetime.now(UTC),
                details={"extra_settings": connection.extra_settings or {}},
            )
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
                has_status_column=bool(probe.get("has_status_column")),
            )
            if not sample:
                return DiagnosticsResult(
                    ok=False,
                    message="Aurora CSV head has no parseable free-number row",
                    checked_at=datetime.now(UTC),
                    details={**probe, **meta},
                    raw=raw,
                )
            files = probe.get("files") or []
            return DiagnosticsResult(
                ok=True,
                message=(
                    f"Aurora CSV OK (files={len(files)}, encoding={meta.get('encoding')}, "
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
                    "urls": [e.url for e in client.csv_files],
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
        files = client.csv_files
        total_files = len(files)
        file_names = [contract.csv_filename(e.url) for e in files]
        await emit_progress(
            on_progress,
            f"Aurora: {total_files} CSV ({', '.join(file_names)})",
            0,
            total_files,
        )

        all_parsed: list[Any] = []
        unmapped_raw: list[dict[str, Any]] = []
        file_metas: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        cumulative_rows = 0

        for idx, entry in enumerate(files, start=1):
            url = entry.url
            fname = contract.csv_filename(url)
            await emit_progress(
                on_progress,
                f"Aurora: скачивание {idx}/{total_files} {fname}",
                idx - 1,
                total_files,
            )
            raw = await client.fetch_csv(url)
            await emit_progress(
                on_progress,
                f"Aurora: разбор {idx}/{total_files} {fname}",
                idx - 1,
                total_files,
            )
            try:
                parsed_items, file_unmapped, meta = parser.parse_free_csv(
                    raw,
                    raw_bytes=client.raw_bytes(raw),
                    filename=fname,
                    has_status_column=entry.has_status_column,
                )
            except ProviderParseError as exc:
                raise ProviderParseError(
                    f"Aurora parse failed for {fname}: {exc}",
                    details={"file": fname, "url": url},
                ) from exc

            bytes_len = int((raw.body_json or {}).get("bytes_len") or 0)
            row_count = int(meta.get("row_count") or 0)
            cumulative_rows += row_count
            logger.warning(
                "Aurora CSV file=%s url=%s bytes=%s rows=%s parsed=%s unmapped=%s "
                "encoding=%s status_col=%s ms=%s",
                fname,
                url,
                bytes_len,
                row_count,
                len(parsed_items),
                len(file_unmapped),
                meta.get("encoding"),
                entry.has_status_column,
                raw.elapsed_ms,
            )
            file_metas.append(
                {
                    "file": fname,
                    "url": url,
                    "bytes": bytes_len,
                    "rows": row_count,
                    "parsed": len(parsed_items),
                    "unmapped": len(file_unmapped),
                    "encoding": meta.get("encoding"),
                    "has_status_column": entry.has_status_column,
                    "elapsed_ms": raw.elapsed_ms,
                }
            )
            envelopes.append(
                RawHttpResult(
                    status_code=raw.status_code,
                    body_text="",
                    body_json={
                        "file": fname,
                        "bytes_len": bytes_len,
                        "encoding": meta.get("encoding"),
                        "row_count": row_count,
                    },
                    headers={},
                    elapsed_ms=raw.elapsed_ms,
                    request_url=raw.request_url,
                )
            )
            unmapped_raw.extend(file_unmapped)
            all_parsed.extend(parsed_items)

            await emit_progress(
                on_progress,
                (
                    f"Aurora: {fname} разобрано {len(parsed_items)} "
                    f"(encoding={meta.get('encoding')}, rows={row_count})"
                ),
                cumulative_rows,
                None,
            )

        mapped = []
        for item in all_parsed:
            mapped_item = mapper.map_number(item)
            if mapped_item:
                mapped.append(mapped_item)
            else:
                unmapped_raw.append(item.raw_payload)

        await emit_progress(
            on_progress,
            f"Aurora: итого {len(mapped)} номеров (files={total_files})",
            len(mapped),
            cumulative_rows or None,
        )

        return SyncResult(
            fetched=cumulative_rows,
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
            warnings=[
                f"files={total_files}",
                f"unmapped={len(unmapped_raw)}",
                *[f"{m['file']}={m['parsed']}" for m in file_metas],
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
