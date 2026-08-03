"""Parse Runexis responses. Envelope/examples from Runexis.html."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.dto.common import RawHttpResult
from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.errors import ProviderAuthError, ProviderParseError
from app.providers.runexis import contract


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _nested_label(value: Any) -> str | None:
    """Display label for nested DIDAPI objects: name → mnemonic → id."""
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "mnemonic", "id"):
            if value.get(key) is not None and str(value.get(key)).strip() != "":
                return str(value.get(key))
        return None
    text = _as_text(value)
    return text if text and text.strip() and text != "null" else None


def _data_list(raw: RawHttpResult) -> list[dict[str, Any]]:
    if raw.status_code == 401:
        raise ProviderAuthError("Runexis unauthorized (401)")
    body = raw.body_json
    if not isinstance(body, dict):
        raise ProviderParseError("Runexis response is not a JSON object")
    if body.get("success") is False:
        raise ProviderParseError(f"Runexis success=false: {body.get('message')}")
    data = body.get("data")
    if data is None:
        return []
    if not isinstance(data, list):
        raise ProviderParseError("Runexis data is not a list")
    return [x for x in data if isinstance(x, dict)]


def parse_me(raw: RawHttpResult) -> dict[str, Any]:
    if raw.status_code == 401:
        raise ProviderAuthError("Runexis unauthorized (401)")
    if raw.status_code >= 400:
        raise ProviderParseError(f"Runexis me failed status={raw.status_code}")
    body = raw.body_json
    if not isinstance(body, dict):
        raise ProviderParseError("Runexis me response not JSON object")
    return body


def parse_auth_tokens(raw: RawHttpResult) -> dict[str, str]:
    """Parse login/refresh token envelope. EXAMPLE-CONFIRMED keys under data."""
    if raw.status_code == 401:
        raise ProviderAuthError("Runexis auth rejected (401)")
    if raw.status_code >= 400:
        raise ProviderAuthError(f"Runexis auth failed status={raw.status_code}: {raw.body_text[:300]}")
    body = raw.body_json
    if not isinstance(body, dict):
        raise ProviderParseError("Runexis auth response is not a JSON object")
    if body.get("success") is False:
        raise ProviderAuthError(f"Runexis auth success=false: {body.get('message')}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise ProviderParseError("Runexis auth data is not an object")
    token = data.get("token")
    if not token:
        raise ProviderParseError("Runexis auth response missing data.token")
    out: dict[str, str] = {"token": str(token)}
    if data.get("refresh_token") is not None:
        out["refresh_token"] = str(data["refresh_token"])
    if data.get("token_expire") is not None:
        out["token_expire"] = str(data["token_expire"])
    if data.get("refresh_token_expire") is not None:
        out["refresh_token_expire"] = str(data["refresh_token_expire"])
    return out


def parse_regions(raw: RawHttpResult) -> list[ParsedRegion]:
    # EXAMPLE-CONFIRMED: id, name
    out: list[ParsedRegion] = []
    for item in _data_list(raw):
        out.append(
            ParsedRegion(
                raw_payload=item,
                region_external_id=_as_text(item.get("id")),
                name=_as_text(item.get("name"))
            )
        )
    return out


def parse_cities(raw: RawHttpResult) -> list[ParsedCity]:
    # EXAMPLE-CONFIRMED: city_id, city_name, region_id, region_name
    out: list[ParsedCity] = []
    for item in _data_list(raw):
        out.append(
            ParsedCity(
                raw_payload=item,
                city_external_id=_as_text(item.get("city_id")),
                name=_as_text(item.get("city_name")),
                region_external_id=_as_text(item.get("region_id")),
                region_name=_as_text(item.get("region_name"))
            )
        )
    return out


def _parse_price(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _extract_price(item: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    # EXAMPLE-CONFIRMED camelCase in docs; live may use snake_case
    for key in (
        "subscriptionFee",
        "subscription_fee",
        "meraPrice",
        "mera_price",
        "installationCost",
        "installation_cost",
    ):
        if item.get(key) is not None:
            return _parse_price(item.get(key)), key
    return None, None


def assemble_msisdn(code: str | None, number: str | None) -> str | None:
    """DERIVED: 7 + code + number (book/buy use 11-digit values starting with 7)."""
    if not code or not number:
        return None
    code_s = str(code).strip()
    number_s = str(number).strip()
    if number_s.startswith("7") and len(number_s) == 11 and number_s.isdigit():
        return number_s
    if not code_s or not number_s:
        return None
    return f"7{code_s}{number_s}"


def status_mnemonic(item: dict[str, Any]) -> str | None:
    status = item.get("status")
    if not isinstance(status, dict):
        return None
    return _as_text(status.get("mnemonic"))


def parse_management_items(raw: RawHttpResult) -> list[ParsedNumberItem]:
    """Parse one page of GET api/v1/numbers/management."""
    out: list[ParsedNumberItem] = []
    for item in _data_list(raw):
        code = _as_text(item.get("code"))
        number = _as_text(item.get("number"))
        msisdn = assemble_msisdn(code, number)
        ext_id = _as_text(item.get("id"))
        key = msisdn or ext_id
        city = item.get("city") if isinstance(item.get("city"), dict) else {}
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        price, price_key = _extract_price(item)
        mnemonic = _as_text(status.get("mnemonic"))
        status_name = _as_text(status.get("name"))
        tariff = _nested_label(item.get("tariff"))
        number_class = _nested_label(item.get("class"))
        operator = _nested_label(item.get("operator"))
        partner = _nested_label(item.get("partner"))
        project = _nested_label(item.get("project"))
        equipment = _nested_label(item.get("equipment"))
        out.append(
            ParsedNumberItem(
                raw_payload=item,
                provider_number_key=key,
                msisdn=msisdn,
                city_external_id=_as_text(city.get("id")),
                city_name=_as_text(city.get("name")),
                buy_price=price,
                period_price=None,
                status_raw=mnemonic or status_name,
                tariff=tariff,
                number_class=number_class,
                operator=operator,
                partner=partner,
                project=project,
                equipment=equipment
            )
        )
    return out


def is_free_management_item(item: dict[str, Any] | ParsedNumberItem) -> bool:
    if isinstance(item, ParsedNumberItem):
        raw = item.raw_payload
        mnemonic = status_mnemonic(raw) or item.status_raw
    else:
        mnemonic = status_mnemonic(item)
    return (mnemonic or "").lower() == contract.STATUS_MNEMONIC_FREE


def is_numbering_free_status(status: Any) -> bool:
    """
    True only for Numbering access_state free / 0.

    Sold (3), installed/отрулен (4), reserved, booked, etc. must not enter
    the free catalog — those are not «Свободные номера».
    """
    if status is None:
        return True
    if isinstance(status, (list, tuple)):
        if not status:
            return True
        return all(is_numbering_free_status(x) for x in status)
    text = str(status).strip().lower()
    if not text:
        return True
    return text in contract.NUMBERING_FREE_STATUS_VALUES


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item.get(key) is not None:
            return item.get(key)
    return None


def _numbering_buy_period(
    item: dict[str, Any],
) -> tuple[Decimal | None, Decimal | None]:
    """Live Numbering search_numbers: buy_price + period_price as separate fields."""
    buy = _parse_price(_first_present(item, "buy_price", "buyPrice"))
    period = _parse_price(_first_present(item, "period_price", "periodPrice"))
    return buy, period


def parse_numbering_search_items(items: list[Any]) -> list[ParsedNumberItem]:
    """
    Parse Numbering API search_numbers result list.
    Item schema is sparse in DOCX — flexible extraction; preserve raw.
    Doc: Runexis-Numbering-API.docx / runexis-numbering-api-contract.md
    """
    out: list[ParsedNumberItem] = []
    for raw_item in items:
        if isinstance(raw_item, str):
            digits = "".join(ch for ch in raw_item if ch.isdigit())
            city_code = digits[:3] if len(digits) >= 10 else None
            phone = digits[3:] if len(digits) >= 10 else digits or None
            item = {
                "city_code": city_code,
                "phone_number": phone,
                "number_raw": raw_item,
            }
        elif isinstance(raw_item, dict):
            item = raw_item
        else:
            continue

        city_code = _as_text(
            _first_present(item, "city_code", "cityCode", "code", "region_code")
        )
        phone = _as_text(
            _first_present(
                item, "phone_number", "phoneNumber", "number", "phone", "msisdn"
            )
        )
        full_number = _as_text(
            _first_present(item, "full_number", "fullNumber", "msisdn")
        )
        # Live Numbering shape: full_number is complete MSISDN; prefer it
        if full_number and full_number.isdigit() and len(full_number) >= 10:
            msisdn = full_number if full_number.startswith("7") else f"7{full_number}"
            if len(msisdn) == 11 and msisdn.startswith("7"):
                if not city_code:
                    city_code = msisdn[1:4]
                if not phone:
                    phone = msisdn[4:]
        elif phone and phone.isdigit() and len(phone) == 10 and not city_code:
            city_code, phone = phone[:3], phone[3:]
            msisdn = assemble_msisdn(city_code, phone)
        elif phone and phone.isdigit() and len(phone) == 11 and phone.startswith("7"):
            msisdn = phone
            if not city_code:
                city_code = phone[1:4]
                phone = phone[4:]
        else:
            msisdn = assemble_msisdn(city_code, phone)

        # Normalize keys used by persist for code/local
        if city_code is not None:
            item.setdefault("code", city_code)
            item.setdefault("city_code", city_code)
        if phone is not None:
            item.setdefault("number", phone)
            item.setdefault("phone_number", phone)

        status = _as_text(
            _first_present(
                item,
                "access_state",
                "usage_status",
                "usage_statuses",
                "status",
                "state",
            )
        )
        if status is None and item.get("access_state") is None:
            status = "free"
        buy_price, period_price = _numbering_buy_period(item)
        # Live: region_title; docs also mention region_name
        region_name = _as_text(
            _first_present(
                item, "region_title", "region_name", "regionName", "region"
            )
        )
        region_id = _as_text(
            _first_present(item, "region_id", "regionId", "regions")
        )
        city_name = _as_text(_first_present(item, "city_name", "cityName", "city"))
        city_id = _as_text(_first_present(item, "city_id", "cityId"))
        key = msisdn or _as_text(_first_present(item, "id", "number_id")) or (
            f"{city_code}{phone}" if city_code and phone else None
        )
        mask = _as_text(item.get("mask"))
        display_mask = _as_text(item.get("display_mask"))
        book_date_raw = _as_text(item.get("book_date"))
        book_date = (
            None
            if book_date_raw is None or book_date_raw.startswith("0000")
            else book_date_raw
        )
        number_type = _as_text(item.get("number_type"))
        points = _parse_price(item.get("points"))
        date_from = _as_text(item.get("date_from"))
        operator_fas = _as_text(item.get("operator_fas"))
        operator_id = _as_text(item.get("operator_id"))
        last_operation_date = _as_text(item.get("last_operation_date"))
        manager_id = _as_text(item.get("manager_id"))
        notes = _as_text(item.get("notes"))
        abcdef = _as_text(item.get("abcdef"))

        out.append(
            ParsedNumberItem(
                raw_payload=item,
                provider_number_key=key,
                msisdn=msisdn,
                city_external_id=city_id or city_code,
                city_name=city_name,
                region_external_id=region_id,
                region_name=region_name,
                buy_price=buy_price,
                period_price=period_price,
                status_raw=status,
                mask=mask,
                display_mask=display_mask,
                book_date=book_date,
                number_type=number_type,
                points=points,
                date_from=date_from,
                operator_fas=operator_fas,
                operator_id=operator_id,
                last_operation_date=last_operation_date,
                manager_id=manager_id,
                notes=notes,
                abcdef=abcdef
            )
        )
    return out
