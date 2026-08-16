"""Finenumbers REG Contour C — mapping and RTU flags (mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber
from app.providers.finenumbers import contract
from app.providers.finenumbers.reg_mapper import (
    catalog_match_key,
    map_reg_endpoint,
    map_reg_endpoints,
    reg_key_set,
)
from app.modules.sync_engine import persist


def test_map_reg_endpoint_parses_msisdn():
    num = map_reg_endpoint(
        {"id": "1", "endpointNumber": "79001234567", "name": "ep"}
    )
    assert num is not None
    assert num.abc_code == "900"
    assert num.number_local == "1234567"
    assert num.msisdn == "79001234567"
    assert num.inventory_kind == InventoryKind.purchased
    assert num.operator == contract.OPERATOR_DISPLAY_NAME


def test_catalog_match_key_zero_pads_local():
    assert catalog_match_key("900", "1234567", None) == "900|1234567"
    assert catalog_match_key("900", "234567", None) == "900|0234567"


def test_reg_key_set_dedupes():
    a = map_reg_endpoint({"endpointNumber": "73852222205"})
    b = map_reg_endpoint({"endpointNumber": "73852222205"})
    mapped, _ = map_reg_endpoints(
        [
            {"id": "1", "endpointNumber": "73852222205"},
            {"id": "2", "endpointNumber": "73852222205"},
        ]
    )
    assert len(mapped) == 1
    assert len(reg_key_set([a, b])) == 1  # type: ignore[list-item]


def test_apply_rtu_connected_flags_semantics():
    """Four product rules for purchased RTU column."""
    row_fn_frontier = SimpleNamespace(
        abc_code="900",
        number_local="1111111",
        msisdn="79001111111",
        operator=contract.OPERATOR_DISPLAY_NAME,
        rtu_connected=None,
    )
    row_fn_other = SimpleNamespace(
        abc_code="900",
        number_local="2222222",
        msisdn="79002222222",
        operator="MegaFon",
        rtu_connected=None,
    )
    row_other_in_reg = SimpleNamespace(
        abc_code="900",
        number_local="3333333",
        msisdn="79003333333",
        operator="SipOut Op",
        rtu_connected=None,
    )
    row_other_missing = SimpleNamespace(
        abc_code="900",
        number_local="4444444",
        msisdn="79004444444",
        operator="SipOut Op",
        rtu_connected=None,
    )
    reg = {"900|3333333", "900|1111111"}

    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [
        (row_fn_frontier, "finenumbers"),
        (row_fn_other, "finenumbers"),
        (row_other_in_reg, "sipout"),
        (row_other_missing, "sipout"),
    ]
    db.execute.return_value = result

    stats = persist.apply_rtu_connected_flags(db, reg_keys=reg)
    assert row_fn_frontier.rtu_connected == contract.RTU_OWN
    assert row_fn_other.rtu_connected == contract.RTU_EXTERNAL
    assert row_other_in_reg.rtu_connected == contract.RTU_EXTERNAL
    assert row_other_missing.rtu_connected == contract.RTU_NOT_CONNECTED
    assert stats == {"rtu_own": 1, "rtu_external": 2, "rtu_not_connected": 1}


def test_normalized_number_carries_rtu_field():
    n = NormalizedNumber(
        inventory_kind=InventoryKind.purchased,
        provider_number_key="79001234567",
        msisdn="79001234567",
        city_external_id=None,
        region_external_id=None,
        city_name=None,
        region_name=None,
        buy_price=None,
        period_price=None,
        status_raw=None,
        mapping_confidence=MappingConfidence.high,
        normalized_payload={},
        raw_payload={},
        rtu_connected=contract.RTU_OWN,
    )
    assert n.rtu_connected == contract.RTU_OWN
