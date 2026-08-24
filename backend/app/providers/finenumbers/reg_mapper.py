"""Map REG phone endpoints to catalog purchased numbers + match keys."""

from __future__ import annotations

from typing import Any

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber
from app.providers.finenumbers.mapper import msisdn_from_abc_local, parse_msisdn_parts

REG_DESCRIPTION_FIELD = "Описание"


def _read_reg_description(row: dict[str, Any]) -> str | None:
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    raw = data.get(REG_DESCRIPTION_FIELD)
    if raw is None or isinstance(raw, (dict, list)):
        return None
    text = str(raw).strip()
    return text or None


def catalog_match_key(abc_code: str | None, number_local: str | None, msisdn: str | None) -> str | None:
    """Stable key from MSISDN (always 3+7). Fallback: stored abc + zero-padded local."""
    if msisdn:
        parts = parse_msisdn_parts(str(msisdn))
        if parts:
            abc, local = parts
            return f"{abc}|{local:07d}"
        digits = "".join(ch for ch in str(msisdn) if ch.isdigit())
        if digits:
            return f"msisdn|{digits}"
    if abc_code and number_local is not None and str(number_local).strip() != "":
        try:
            local_i = int(str(number_local).strip())
            return f"{str(abc_code).strip()}|{local_i:07d}"
        except (TypeError, ValueError):
            pass
    return None


def map_reg_endpoint(row: dict[str, Any]) -> NormalizedNumber | None:
    """One REG phones item → purchased NormalizedNumber, or None if unparseable."""
    raw_num = row.get("endpointNumber")
    if not raw_num:
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        raw_num = data.get("Номер оконечного оборудования")
    if not raw_num:
        return None
    parts = parse_msisdn_parts(str(raw_num))
    if not parts:
        return None
    abc, local = parts
    msisdn = msisdn_from_abc_local(abc, local)
    number_local = f"{local:07d}"
    description = _read_reg_description(row)
    return NormalizedNumber(
        inventory_kind=InventoryKind.purchased,
        provider_number_key=msisdn,
        msisdn=msisdn,
        city_external_id=None,
        region_external_id=None,
        city_name=None,
        region_name=None,
        buy_price=None,
        period_price=None,
        status_raw=None,
        mapping_confidence=MappingConfidence.high,
        normalized_payload={
            "source": "finenumbers_reg_phones",
            "reg_id": row.get("id"),
            "reg_name": row.get("name"),
            "reg_description": description,
        },
        raw_payload=dict(row),
        abc_code=abc,
        number_local=number_local,
        operator=None,
    )


def map_reg_endpoints(rows: list[dict[str, Any]]) -> tuple[list[NormalizedNumber], list[dict[str, Any]]]:
    mapped: list[NormalizedNumber] = []
    unmapped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        num = map_reg_endpoint(row)
        if num is None:
            if isinstance(row, dict):
                unmapped.append(row)
            continue
        if num.provider_number_key in seen:
            continue
        seen.add(num.provider_number_key)
        mapped.append(num)
    return mapped, unmapped


def reg_key_set(numbers: list[NormalizedNumber]) -> set[str]:
    keys: set[str] = set()
    for n in numbers:
        k = catalog_match_key(n.abc_code, n.number_local, n.msisdn)
        if k:
            keys.add(k)
    return keys


def reg_client_map(numbers: list[NormalizedNumber]) -> dict[str, str]:
    """Phone match key → REG «Описание». First non-empty description wins."""
    out: dict[str, str] = {}
    for n in numbers:
        key = catalog_match_key(n.abc_code, n.number_local, n.msisdn)
        if not key or key in out:
            continue
        payload = n.normalized_payload if isinstance(n.normalized_payload, dict) else {}
        raw = payload.get("reg_description")
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            out[key] = text
    return out
