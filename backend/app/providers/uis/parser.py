"""Parse UIS JSON-RPC envelopes. Docs: uis-contract.md."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.dto.common import RawHttpResult
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.errors import ProviderAuthError, ProviderParseError
from app.providers.msisdn_split import normalize_phone


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_price(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _require_result(raw: RawHttpResult) -> dict[str, Any]:
    if raw.status_code >= 400:
        raise ProviderParseError(f"UIS HTTP {raw.status_code}")
    data = raw.body_json
    if not isinstance(data, dict):
        raise ProviderParseError("UIS response is not a JSON object")
    if "error" in data and data["error"] is not None:
        err = data["error"]
        if not isinstance(err, dict):
            raise ProviderParseError(f"UIS RPC error: {err!r}")
        mnemonic = ""
        err_data = err.get("data")
        if isinstance(err_data, dict):
            mnemonic = str(err_data.get("mnemonic") or "")
        msg = f"UIS RPC error code={err.get('code')} message={err.get('message')} mnemonic={mnemonic}"
        if "access_token" in mnemonic or "auth" in mnemonic.lower():
            raise ProviderAuthError(msg)
        raise ProviderParseError(msg)
    result = data.get("result")
    if not isinstance(result, dict):
        raise ProviderParseError("UIS result is not an object")
    return result


def parse_list_page(raw: RawHttpResult) -> tuple[list[dict[str, Any]], int | None]:
    result = _require_result(raw)
    data = result.get("data")
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ProviderParseError("UIS list result.data is not an array")
    items = [x for x in data if isinstance(x, dict)]
    total: int | None = None
    meta = result.get("metadata")
    if isinstance(meta, dict) and meta.get("total_items") is not None:
        try:
            total = int(meta["total_items"])
        except (TypeError, ValueError):
            total = None
    return items, total


def parse_available_item(item: dict[str, Any]) -> ParsedNumberItem:
    phone = normalize_phone(item.get("phone_number"))
    return ParsedNumberItem(
        raw_payload=item,
        provider_number_key=phone,
        msisdn=phone,
        region_external_id=_as_text(item.get("location_mnemonic")),
        region_name=_as_text(item.get("location_name")),
        buy_price=_parse_price(item.get("onetime_payment")),
        period_price=_parse_price(item.get("monthly_charge")),
        number_type=_as_text(item.get("category")),
    )


def parse_virtual_item(item: dict[str, Any]) -> ParsedNumberItem:
    phone = normalize_phone(item.get("virtual_phone_number"))
    ext_id = item.get("id")
    key = phone
    if not key and ext_id is not None:
        key = f"uis:{ext_id}"
    notes_parts = []
    for field in ("name", "comment"):
        val = _as_text(item.get(field))
        if val:
            notes_parts.append(val)
    return ParsedNumberItem(
        raw_payload=item,
        provider_number_key=key,
        msisdn=phone,
        status_raw=_as_text(item.get("status")),
        number_type=_as_text(item.get("category")),
        notes=" | ".join(notes_parts) if notes_parts else None,
        date_from=_as_text(item.get("activation_date")),
    )
