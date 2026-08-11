"""Runexis orchestrator. Docs: Runexis.html + Runexis-Numbering-API.docx."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.models.enums import InventoryKind, ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncResult
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.runexis import contract, mapper, parser
from app.providers.runexis.client import RunexisClient
from app.providers.runexis.numbering_client import RunexisNumberingClient

logger = logging.getLogger(__name__)


class RunexisProvider(AbstractProvider):
    code = ProviderCode.runexis

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "Numbering API JSON-RPC search_numbers (free)",
                "doc_refs": contract.DOC_REFS_NUMBERING_FREE,
            },
            "purchased_numbers": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET api/v1/numbers/management",
                "doc_refs": contract.DOC_REFS_INVENTORY,
            },
            "dictionaries": {
                "supported": True,
                "source": "documentation_verified",
                "actions": ["GET api/v1/regions", "GET api/v1/regions/cities"],
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "DIDAPI GET me + Numbering connect (when configured)",
                "actions": [
                    "POST api/v1/login",
                    "GET api/v1/me",
                    "Numbering JSON-RPC connect",
                ],
            },
        }

    def _didapi_client(self, connection: ConnectionConfig) -> RunexisClient:
        return RunexisClient(connection)

    def _numbering_client(self, connection: ConnectionConfig) -> RunexisNumberingClient:
        return RunexisNumberingClient(connection)

    @staticmethod
    def _has_didapi_auth(connection: ConnectionConfig) -> bool:
        auth = connection.auth_settings or {}
        return bool(
            auth.get("token")
            or auth.get("access_token")
            or (auth.get("email") and auth.get("password"))
        )

    @staticmethod
    def _has_numbering_auth(connection: ConnectionConfig) -> bool:
        auth = connection.auth_settings or {}
        return bool(
            auth.get(contract.AUTH_NUMBERING_LOGIN)
            and auth.get(contract.AUTH_NUMBERING_PASSWORD)
        )

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        details: dict[str, Any] = {}
        messages: list[str] = []
        oks: list[bool] = []
        last_raw = None

        if not self._has_didapi_auth(connection) and not self._has_numbering_auth(
            connection
        ):
            return DiagnosticsResult(
                ok=False,
                message=(
                    "Runexis: задайте DIDAPI email/password и/или Numbering "
                    "numbering_login/numbering_password"
                ),
                checked_at=datetime.now(timezone.utc),
                details={"configured": []},
            )

        if self._has_didapi_auth(connection):
            try:
                client = self._didapi_client(connection)
                raw = await client.get_me()
                last_raw = raw
                parser.parse_me(raw)
                ok = 200 <= raw.status_code < 300
                oks.append(ok)
                details["didapi"] = {"endpoint": contract.GET_ME, "ok": ok}
                messages.append(
                    "DIDAPI GET api/v1/me OK" if ok else f"DIDAPI me status={raw.status_code}"
                )
            except Exception as exc:
                oks.append(False)
                details["didapi"] = {"endpoint": contract.GET_ME, "ok": False, "error": str(exc)}
                messages.append(f"DIDAPI: {exc}")

        if self._has_numbering_auth(connection):
            try:
                # READ-ONLY: connect only
                nclient = self._numbering_client(connection)
                session = await nclient.connect()
                oks.append(True)
                details["numbering"] = {
                    "method": contract.NUMBERING_METHOD_CONNECT,
                    "ok": True,
                    "base_url": nclient.base_url,
                    "session_preview": f"…{session[-4:]}" if len(session) > 4 else "****",
                }
                messages.append("Numbering connect OK")
            except Exception as exc:
                oks.append(False)
                details["numbering"] = {
                    "method": contract.NUMBERING_METHOD_CONNECT,
                    "ok": False,
                    "error": str(exc),
                }
                messages.append(f"Numbering: {exc}")

        ok = all(oks) if oks else False
        return DiagnosticsResult(
            ok=ok,
            message="; ".join(messages) if messages else "no checks",
            checked_at=datetime.now(timezone.utc),
            details=details,
            raw=last_raw,
        )

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # VERIFIED: GET api/v1/regions
        from app.providers.progress_emit import emit_progress

        await emit_progress(kwargs.get("on_progress"), "Runexis: regions…")
        client = self._didapi_client(connection)
        raw = await client.get_regions()
        regions = parser.parse_regions(raw)
        return SyncResult(
            fetched=len(regions),
            parsed=len(regions),
            items={"regions": regions, "cities": []},
            raw_envelopes=[raw],
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # VERIFIED: GET api/v1/regions/cities
        from app.providers.progress_emit import emit_progress

        await emit_progress(kwargs.get("on_progress"), "Runexis: cities…")
        client = self._didapi_client(connection)
        raw = await client.get_cities()
        cities = parser.parse_cities(raw)
        return SyncResult(
            fetched=len(cities),
            parsed=len(cities),
            items={"regions": [], "cities": cities},
            raw_envelopes=[raw],
        )

    def _map_items(
        self,
        items: list[ParsedNumberItem],
        *,
        inventory_kind: InventoryKind,
        city_lookup: dict[str, tuple],
    ) -> tuple[list, list[dict]]:
        mapped = []
        unmapped_raw: list[dict] = []
        for item in items:
            region_name = item.region_name
            region_id = item.region_external_id
            if item.city_external_id and item.city_external_id in city_lookup:
                tup = city_lookup[item.city_external_id]
                region_id = region_id or (tup[1] if len(tup) > 1 else None)
                region_name = region_name or (tup[2] if len(tup) > 2 else None)
                if not item.city_name and tup:
                    item.city_name = tup[0]
            mapped_item = mapper.map_number(
                item,
                inventory_kind=inventory_kind,
                region_name=region_name,
                region_external_id=region_id,
            )
            if mapped_item:
                mapped.append(mapped_item)
            else:
                unmapped_raw.append(item.raw_payload)
        return mapped, unmapped_raw

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # VERIFIED sole source: Numbering API search_numbers (Runexis-Numbering-API.docx)
        if not self._has_numbering_auth(connection):
            raise ProviderAuthError(
                "Runexis free sync requires numbering_login and numbering_password "
                "(Numbering API — separate credentials)."
            )
        from app.providers.progress_emit import emit_progress

        on_progress = kwargs.get("on_progress")
        try:
            nclient = self._numbering_client(connection)
            raw_items, envelopes, meta = await nclient.list_all_free_numbers(
                on_progress=on_progress
            )
        except (ProviderAuthError, ProviderTransportError, ProviderError):
            raise
        await emit_progress(
            on_progress, "Runexis: разбор и маппинг…", len(raw_items), len(raw_items)
        )
        access_state_distribution = Counter()
        for raw in raw_items:
            if isinstance(raw, dict):
                state = raw.get("access_state")
                access_state_distribution[str(state if state is not None else "")] += 1

        parsed = parser.parse_numbering_search_items(raw_items)
        free_parsed = []
        dropped_non_free = 0
        for item in parsed:
            if parser.is_numbering_free_status(item.status_raw):
                # Normalize numeric/empty free markers for stable UI facets.
                item.status_raw = contract.STATUS_MNEMONIC_FREE
                free_parsed.append(item)
            else:
                dropped_non_free += 1
        city_lookup: dict[str, tuple] = kwargs.get("city_lookup") or {}
        mapped, unmapped_raw = self._map_items(
            free_parsed, inventory_kind=InventoryKind.free, city_lookup=city_lookup
        )
        raw_fetched = int(meta.get("raw_fetched") or meta.get("fetched") or len(raw_items))
        count_hint = int(meta.get("count_hint") or meta.get("expected_count") or 0)
        count_hint_gap = int(
            meta.get("count_hint_gap")
            if meta.get("count_hint_gap") is not None
            else max(0, count_hint - raw_fetched)
        )
        integrity = {
            "raw_fetched": raw_fetched,
            "free_kept": len(free_parsed),
            "dropped_non_free_status": dropped_non_free,
            "map_failed": len(unmapped_raw),
            "access_state_distribution": dict(access_state_distribution),
            "sequential_verify": bool(meta.get("sequential_verify")),
            "final_short_page_offset": meta.get("final_short_page_offset"),
            "count_hint": count_hint,
            "count_hint_gap": count_hint_gap,
            "count_is_progress_hint": True,
            "filter": meta.get("filter"),
        }
        warnings = [
            "Free catalog via Numbering API search_numbers (separate numbering_* credentials)",
            f"filter_used={meta.get('filter')}",
            f"count_hint={count_hint}",
            f"raw_fetched={raw_fetched}",
            f"free_kept={len(free_parsed)}",
            f"dropped_non_free_status={dropped_non_free}",
            f"map_failed={len(unmapped_raw)}",
            f"count_hint_gap={count_hint_gap} (info; count is progress hint, not fail)",
            f"sequential_verify={meta.get('sequential_verify')}",
            f"final_short_page_offset={meta.get('final_short_page_offset')}",
            f"access_state_distribution={dict(access_state_distribution)}",
        ]
        if meta.get("primary_filter_error"):
            warnings.append(
                f"primary filter failed, used fallback: {meta.get('primary_filter_error')}"
            )
        logger.warning("Runexis free integrity %s", integrity)
        return SyncResult(
            fetched=len(free_parsed),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
            warnings=warnings,
            extra_stats={"integrity": integrity},
        )

    async def sync_purchased_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # VERIFIED: GET api/v1/numbers/management — partner numbers excluding free
        from app.providers.progress_emit import emit_progress

        on_progress = kwargs.get("on_progress")
        client = self._didapi_client(connection)
        _raw_items, envelopes = await client.list_all_numbers_management(
            on_progress=on_progress
        )
        await emit_progress(
            on_progress, "Runexis: разбор и маппинг…", len(_raw_items), len(_raw_items)
        )
        parsed = [
            p
            for env in envelopes
            for p in parser.parse_management_items(env)
            if not parser.is_free_management_item(p)
        ]
        city_lookup: dict[str, tuple] = kwargs.get("city_lookup") or {}
        mapped, unmapped_raw = self._map_items(
            parsed, inventory_kind=InventoryKind.purchased, city_lookup=city_lookup
        )
        return SyncResult(
            fetched=len(parsed),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            raw_envelopes=envelopes,
        )
