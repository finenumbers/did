"""Parse Novofon JSON-RPC envelopes. Docs: novofon-contract.md."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.dto.common import RawHttpResult
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.errors import ProviderAuthError, ProviderError, ProviderParseError
from app.providers.msisdn_split import normalize_phone
from app.providers.novofon import contract


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


def _error_parts(raw: RawHttpResult) -> tuple[dict[str, Any], str, dict[str, Any]] | None:
    data = raw.body_json
    if not isinstance(data, dict) or data.get("error") in (None, ""):
        return None
    err = data["error"]
    if not isinstance(err, dict):
        raise ProviderParseError(f"Novofon RPC error: {err!r}")
    err_data = err.get("data") if isinstance(err.get("data"), dict) else {}
    mnemonic = str(err_data.get("mnemonic") or "")
    return err, mnemonic, err_data


def limit_retry_wait(raw: RawHttpResult) -> float | None:
    """Seconds to wait before one retry, or None when the call must fail."""
    parts = _error_parts(raw)
    if parts is None:
        return None
    err, mnemonic, err_data = parts
    if mnemonic != "limit_exceeded":
        return None
    params = err_data.get("params") if isinstance(err_data.get("params"), dict) else {}
    limit_type = str(params.get("limit_type") or "").lower()
    message = str(err.get("message") or "").lower()
    if limit_type == "day" or "per day" in message:
        return None
    meta = err_data.get("metadata") if isinstance(err_data.get("metadata"), dict) else {}
    limits = meta.get("limits") if isinstance(meta.get("limits"), dict) else {}
    reset = limits.get("minute_reset")
    try:
        seconds = float(reset)
    except (TypeError, ValueError):
        return None
    minute = limit_type == "minute" or "minute" in message or "minute" in limit_type
    if minute and 0 < seconds <= contract.LIMIT_RETRY_MAX_SECONDS:
        return seconds
    return None


# These mnemonics mean the method is not for this token. They are not auth failures.
NOT_AUDIENCE_MNEMONICS = frozenset({"forbidden", "method_not_found"})
# Live Novofon uses this code for component_disabled; the HTML names method_component_disabled.
COMPONENT_ERROR_CODE = -32008


def _raise_rpc(err: dict[str, Any], mnemonic: str) -> None:
    msg = (
        f"Novofon RPC error code={err.get('code')} "
        f"message={err.get('message')} mnemonic={mnemonic}"
    )
    if "access_token" in mnemonic or "auth" in mnemonic.lower():
        raise ProviderAuthError(msg)
    if mnemonic == "limit_exceeded":
        raise ProviderError(msg, code="NOVOFON_LIMIT_EXCEEDED")
    raise ProviderParseError(msg)


def _is_component_error(err: dict[str, Any]) -> bool:
    try:
        return int(err.get("code")) == COMPONENT_ERROR_CODE
    except (TypeError, ValueError):
        return False


def audience_or_result(
    raw: RawHttpResult,
    *,
    soften_component: bool = False,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Success result, or (None, mnemonic, component_group) when the token cannot call it.

    Auth, IP, limit, and other RPC errors still raise. `soften_component` is only
    for the partner probe and the account probe that follows a component miss:
    error code -32008 becomes a miss instead of a parse error. Number reads keep
    the default and surface the server message.
    """
    if raw.status_code >= 400:
        raise ProviderParseError(f"Novofon HTTP {raw.status_code}")
    parts = _error_parts(raw)
    if parts is not None:
        err, mnemonic, _err_data = parts
        component = _is_component_error(err)
        if mnemonic in NOT_AUDIENCE_MNEMONICS or (soften_component and component):
            return None, mnemonic or "component_disabled", component
        _raise_rpc(err, mnemonic)
    data = raw.body_json
    if not isinstance(data, dict):
        raise ProviderParseError("Novofon response is not a JSON object")
    result = data.get("result")
    if not isinstance(result, dict):
        raise ProviderParseError("Novofon result is not an object")
    return result, None, False


def _require_result(raw: RawHttpResult) -> dict[str, Any]:
    result, missed, _component = audience_or_result(raw)
    if missed is not None or result is None:
        raise ProviderParseError(f"Novofon RPC error mnemonic={missed or 'empty_result'}")
    return result


def result_limits(result: dict[str, Any]) -> dict[str, Any]:
    for key in ("metadata", "meta_data"):
        meta = result.get(key)
        if isinstance(meta, dict) and isinstance(meta.get("limits"), dict):
            return dict(meta["limits"])
    return {}


def parse_account(result: dict[str, Any]) -> dict[str, Any] | None:
    data = result.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    row = data[0]
    try:
        app_id = int(row["app_id"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"app_id": app_id, "name": _as_text(row.get("name")) or ""}


def parse_customer_users(result: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    data = result.get("data")
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ProviderParseError("Novofon get.customer_users result.data is not an array")
    users: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            user_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        customer_id = item.get("customer_id")
        try:
            customer_out = int(customer_id) if customer_id is not None else None
        except (TypeError, ValueError):
            customer_out = None
        users.append(
            {
                "id": user_id,
                "name": _as_text(item.get("name")) or "",
                "login": _as_text(item.get("login")) or "",
                "customer_id": customer_out,
            }
        )
    return users, _total_items(result)


def customer_users_are_agent(result: dict[str, Any]) -> tuple[bool, int | None]:
    """A non-empty partner list means the token is an agent. An empty success does not."""
    total = _total_items(result)
    data = result.get("data")
    nonempty = isinstance(data, list) and any(isinstance(row, dict) for row in data)
    if total is not None and total > 0:
        return True, total
    if total is None and nonempty:
        return True, None
    return False, total


def _total_items(result: dict[str, Any]) -> int | None:
    for key in ("metadata", "meta_data"):
        meta = result.get(key)
        if isinstance(meta, dict) and meta.get("total_items") is not None:
            try:
                return int(meta["total_items"])
            except (TypeError, ValueError):
                return None
    return None


def parse_list_page(raw: RawHttpResult) -> tuple[list[dict[str, Any]], int | None]:
    result = _require_result(raw)
    data = result.get("data")
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ProviderParseError("Novofon list result.data is not an array")
    items = [x for x in data if isinstance(x, dict)]
    return items, _total_items(result)


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
    return ParsedNumberItem(
        raw_payload=item,
        provider_number_key=phone,
        msisdn=phone,
        status_raw=_as_text(item.get("status")),
        number_type=_as_text(item.get("category")),
        date_from=_as_text(item.get("activation_date")),
    )
