"""Novofon Data API orchestrator. Docs: novofon-contract.md — read-only."""

from __future__ import annotations

import logging
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
from app.providers.novofon import contract, mapper, parser
from app.providers.novofon.client import NovofonClient, NovofonPrincipal
from app.providers.novofon.user_api import (
    NovofonUserApi,
    OrderShop,
    UserApiError,
    UserApiRefusal,
    load_order_shop,
)

logger = logging.getLogger(__name__)


class NovofonProvider(AbstractProvider):
    code = ProviderCode.novofon

    def __init__(self) -> None:
        self._principal: NovofonPrincipal | None = None

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

    def _client(self, connection: ConnectionConfig) -> NovofonClient:
        return NovofonClient(connection)

    async def _open(
        self, connection: ConnectionConfig
    ) -> tuple[NovofonClient, NovofonPrincipal]:
        client = self._client(connection)
        if self._principal is None:
            self._principal = await client.resolve_principal()
        else:
            client.adopt_principal(self._principal)
        return client, self._principal

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        checked = (
            contract.METHOD_VIRTUAL_NUMBERS,
            contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS,
        )
        try:
            client, principal = await self._open(connection)
            totals: dict[str, int | None] = {}
            for method in checked:
                raw = await client.get_page(method, offset=0, limit=1)
                _items, total = parser.parse_list_page(raw)
                totals[method] = total
            parts = [principal.summary]
            parts.extend(f"{method} total_items={total}" for method, total in totals.items())
            auth = connection.auth_settings or {}
            if not str(auth.get(contract.AUTH_API_KEY) or "").strip():
                parts.append(contract.KEY_MISSING_MESSAGE)
                return DiagnosticsResult(
                    ok=False,
                    message="; ".join(parts),
                    checked_at=datetime.now(UTC),
                    details={
                        "methods": list(checked),
                        "principal": principal.as_dict(),
                        "totals": totals,
                    },
                )
            try:
                countries = await NovofonUserApi(connection).countries()
            except UserApiError as exc:
                parts.append(str(exc))
                return DiagnosticsResult(
                    ok=False,
                    message="; ".join(parts),
                    checked_at=datetime.now(UTC),
                    details={
                        "methods": list(checked),
                        "principal": principal.as_dict(),
                        "totals": totals,
                    },
                )
            parts.append(f"{contract.USER_API_COUNTRIES} стран={len(countries)}")
            return DiagnosticsResult(
                ok=True,
                message="; ".join(parts),
                checked_at=datetime.now(UTC),
                details={
                    "methods": list(checked),
                    "principal": principal.as_dict(),
                    "totals": totals,
                    "countries": len(countries),
                },
            )
        except Exception as exc:  # noqa: BLE001 — surface any probe failure to UI
            return DiagnosticsResult(
                ok=False,
                message=str(exc),
                checked_at=datetime.now(UTC),
                details={"methods": list(checked)},
            )

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider=self.code.value,
                    capability="dictionaries",
                    message="Novofon Data API has no regions/cities dictionary for virtual numbers",
                    doc_refs=["docs/providers/novofon-contract.md"],
                )
            ]
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return await self.sync_regions(connection, **kwargs)

    async def _sync_method(
        self,
        connection: ConnectionConfig,
        *,
        method: str,
        inventory_kind: InventoryKind,
        parse_item: Any,
        on_progress: Any | None,
    ) -> SyncResult:
        from app.providers.progress_emit import emit_progress

        client, principal = await self._open(connection)
        items, _envelopes, page_integrity = await client.iter_all(
            method, on_progress=on_progress
        )
        limits = page_integrity.get("limits") if isinstance(page_integrity.get("limits"), dict) else {}
        logger.info(
            "Novofon %s %s total_items=%s minute_remaining=%s day_remaining=%s",
            method,
            principal.summary,
            page_integrity.get("total_items"),
            limits.get("minute_remaining"),
            limits.get("day_remaining"),
        )
        await emit_progress(on_progress, "Novofon: разбор и маппинг", 0, len(items) or None)
        mapped = []
        unmapped_raw: list[dict] = []
        for item in items:
            parsed = parse_item(item)
            mapped_item = mapper.map_number(parsed, inventory_kind=inventory_kind)
            if mapped_item:
                mapped.append(mapped_item)
            else:
                unmapped_raw.append(item)
        warnings: list[str] = []
        if page_integrity.get("total_items_mismatch"):
            warnings.append(
                "Novofon total_items mismatch: "
                f"fetched={page_integrity.get('fetched')} "
                f"total_items={page_integrity.get('total_items')}"
            )
        return SyncResult(
            fetched=len(items),
            parsed=len(mapped),
            items=mapped,
            unmapped_raw=unmapped_raw,
            warnings=warnings,
            extra_stats={"integrity": page_integrity, "principal": principal.as_dict()},
        )

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        data = await self._sync_method(
            connection,
            method=contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS,
            inventory_kind=InventoryKind.free,
            parse_item=parser.parse_available_item,
            on_progress=kwargs.get("on_progress"),
        )
        try:
            shop = await load_order_shop(connection, on_progress=kwargs.get("on_progress"))
        except UserApiRefusal as exc:
            logger.warning("Novofon shop refused: %s", exc.message)
            return _refuse_free(data, exc.message)
        return _combine_free(data, shop)

    async def sync_purchased_numbers(
        self, connection: ConnectionConfig, **kwargs: Any
    ) -> SyncResult:
        return await self._sync_method(
            connection,
            method=contract.METHOD_VIRTUAL_NUMBERS,
            inventory_kind=InventoryKind.purchased,
            parse_item=parser.parse_virtual_item,
            on_progress=kwargs.get("on_progress"),
        )


def _refuse_free(data: SyncResult, message: str) -> SyncResult:
    """Shop was not read. Do not persist the Data API pool as if it were the full free slice."""
    extra = dict(data.extra_stats or {})
    extra["refusal_detail"] = message
    extra["shop"] = {"read": False}
    return SyncResult(
        fetched=0,
        parsed=0,
        items=[],
        warnings=[message],
        extra_stats=extra,
    )


def _combine_free(data: SyncResult, shop: OrderShop) -> SyncResult:
    seen: set[str] = set()
    items: list[Any] = []
    for item in data.items or []:
        key = getattr(item, "provider_number_key", None)
        if key and key not in seen:
            seen.add(key)
            items.append(item)
    for item in shop.mapped:
        key = item.provider_number_key
        if key and key not in seen:
            seen.add(key)
            items.append(item)
    warnings = list(data.warnings or [])
    extra = dict(data.extra_stats or {})
    extra["shop"] = {
        "directions": shop.directions,
        "numbers": shop.raw_count,
        "min_per_direction": shop.min_per_direction,
        "max_per_direction": shop.max_per_direction,
        "hmac_secret": shop.secret_slot,
        "russia_missing": shop.russia_missing,
    }
    if not warnings and not items:
        integrity = extra.get("integrity")
        total = integrity.get("total_items") if isinstance(integrity, dict) else None
        if shop.russia_missing:
            extra["empty_suffix"] = (
                f"Data API total_items={total}; витрина: в списке стран нет RU"
            )
        else:
            extra["empty_suffix"] = (
                f"Data API total_items={total}; "
                f"витрина: направлений={shop.directions}, номеров={shop.raw_count}"
            )
    logger.info(
        "Novofon shop directions=%s numbers=%s min=%s max=%s hmac_secret=%s russia_missing=%s",
        shop.directions,
        shop.raw_count,
        shop.min_per_direction,
        shop.max_per_direction,
        shop.secret_slot,
        shop.russia_missing,
    )
    return SyncResult(
        fetched=int(data.fetched or 0) + shop.raw_count,
        parsed=len(items),
        items=items,
        unmapped_raw=[*list(data.unmapped_raw or []), *shop.unmapped],
        warnings=warnings,
        extra_stats=extra,
    )
