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
    OwnedNumbers,
    UserApiError,
    load_owned_numbers,
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
            details: dict[str, Any] = {
                "methods": list(checked),
                "principal": principal.as_dict(),
                "totals": totals,
            }
            if not str(auth.get(contract.AUTH_API_KEY) or "").strip():
                details["owned"] = "skipped"
                return DiagnosticsResult(
                    ok=True,
                    message="; ".join(parts),
                    checked_at=datetime.now(UTC),
                    details=details,
                )
            api = NovofonUserApi(connection)
            try:
                owned_rows = await api.owned()
            except UserApiError as exc:
                parts.append(str(exc))
                details["owned"] = {"read": False}
                return DiagnosticsResult(
                    ok=False,
                    message="; ".join(parts),
                    checked_at=datetime.now(UTC),
                    details=details,
                )
            parts.append(f"{contract.USER_API_OWNED} номеров={len(owned_rows)}")
            details["owned"] = len(owned_rows)
            return DiagnosticsResult(
                ok=True,
                message="; ".join(parts),
                checked_at=datetime.now(UTC),
                details=details,
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
        reason = _free_incomplete(data)
        if reason:
            logger.warning("Novofon free incomplete: %s", reason)
            extra = dict(data.extra_stats or {})
            extra["refusal_detail"] = reason
            return SyncResult(
                fetched=0,
                parsed=0,
                items=[],
                warnings=[reason],
                extra_stats=extra,
            )
        if not data.items and not data.warnings:
            extra = dict(data.extra_stats or {})
            integrity = extra.get("integrity")
            total = integrity.get("total_items") if isinstance(integrity, dict) else None
            extra["empty_suffix"] = (
                f"{contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS} total_items={total}"
            )
            return SyncResult(
                fetched=int(data.fetched or 0),
                parsed=int(data.parsed or 0),
                items=[],
                unmapped_raw=list(data.unmapped_raw or []),
                warnings=[],
                extra_stats=extra,
            )
        return data

    async def sync_purchased_numbers(
        self, connection: ConnectionConfig, **kwargs: Any
    ) -> SyncResult:
        data = await self._sync_method(
            connection,
            method=contract.METHOD_VIRTUAL_NUMBERS,
            inventory_kind=InventoryKind.purchased,
            parse_item=parser.parse_virtual_item,
            on_progress=kwargs.get("on_progress"),
        )
        auth = connection.auth_settings or {}
        if not str(auth.get(contract.AUTH_API_KEY) or "").strip():
            return data
        try:
            owned = await load_owned_numbers(connection, on_progress=kwargs.get("on_progress"))
        except UserApiError as exc:
            message = (
                "Список купленных номеров кабинета не прочитан: "
                f"{exc}. Пул Data API в этом прогоне не записан."
            )
            logger.warning("Novofon owned list refused: %s", message)
            extra = dict(data.extra_stats or {})
            extra["refusal_detail"] = message
            extra["owned"] = {"read": False}
            return SyncResult(
                fetched=0,
                parsed=0,
                items=[],
                warnings=[message],
                extra_stats=extra,
            )
        return _combine_purchased(data, owned)


def _free_incomplete(data: SyncResult) -> str | None:
    """Refuse a free slice that is shorter than total_items or has an unmapped row."""
    extra = data.extra_stats if isinstance(data.extra_stats, dict) else {}
    integrity = extra.get("integrity")
    integrity = integrity if isinstance(integrity, dict) else {}
    total = integrity.get("total_items")
    fetched = integrity.get("fetched")
    if fetched is None:
        fetched = data.fetched
    incomplete = bool(integrity.get("total_items_mismatch")) or total is None or fetched != total
    if incomplete:
        return (
            f"{contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS} прочитан не целиком: "
            f"fetched={fetched} total_items={total}"
        )
    unmapped = list(data.unmapped_raw or [])
    if unmapped:
        return (
            f"{contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS}: "
            f"не разобрано номеров={len(unmapped)}. Срез не записан."
        )
    return None


def _combine_purchased(data: SyncResult, owned: OwnedNumbers) -> SyncResult:
    """One row per key. The cabinet row supplies price and place; Data API raw is nested."""
    by_key: dict[str, Any] = {}
    order: list[str] = []
    for item in data.items or []:
        key = getattr(item, "provider_number_key", None)
        if not key or key in by_key:
            continue
        by_key[key] = item
        order.append(key)
    for item in owned.mapped:
        key = item.provider_number_key
        if not key:
            continue
        previous = by_key.get(key)
        if previous is not None:
            raw = dict(item.raw_payload)
            raw["data_api"] = getattr(previous, "raw_payload", None)
            item.raw_payload = raw
        if key not in by_key:
            order.append(key)
        by_key[key] = item
    items = [by_key[key] for key in order]
    extra = dict(data.extra_stats or {})
    extra["owned"] = {
        "read": True,
        "numbers": owned.raw_count,
        "hmac_secret": owned.secret_slot,
    }
    if not data.warnings and not items:
        integrity = extra.get("integrity")
        total = integrity.get("total_items") if isinstance(integrity, dict) else None
        extra["empty_suffix"] = (
            f"Data API total_items={total}; список кабинета: номеров={owned.raw_count}"
        )
    logger.info(
        "Novofon owned numbers=%s hmac_secret=%s",
        owned.raw_count,
        owned.secret_slot,
    )
    return SyncResult(
        fetched=int(data.fetched or 0) + owned.raw_count,
        parsed=len(items),
        items=items,
        unmapped_raw=list(data.unmapped_raw or []),
        warnings=list(data.warnings or []),
        extra_stats=extra,
    )
