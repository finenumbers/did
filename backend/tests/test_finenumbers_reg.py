"""Finenumbers REG Contour C — mapping and RTU flags (mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

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
    early = {"900|1234567"}
    reg = {"900|9999999"}
    row_early_missing = SimpleNamespace(
        abc_code="900",
        number_local="1234567",
        msisdn="79001234567",
        rtu_connected=None,
    )
    row_reg_only = SimpleNamespace(
        abc_code="900",
        number_local="9999999",
        msisdn="79009999999",
        rtu_connected=None,
    )
    row_early_confirmed = SimpleNamespace(
        abc_code="900",
        number_local="1111111",
        msisdn="79001111111",
        rtu_connected=None,
    )
    # early key that is also in reg — should be Подключено
    early2 = {"900|1234567", "900|1111111"}
    reg2 = {"900|1111111", "900|9999999"}

    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        row_early_missing,
        row_reg_only,
        row_early_confirmed,
    ]
    stats = persist.apply_rtu_connected_flags(
        db, reg_keys=reg2, early_purchased_keys=early2
    )
    assert row_early_missing.rtu_connected == contract.RTU_NOT_CONNECTED
    assert row_reg_only.rtu_connected == contract.RTU_CONNECTED
    assert row_early_confirmed.rtu_connected == contract.RTU_CONNECTED
    assert stats["rtu_not_connected"] == 1
    assert stats["rtu_connected"] == 2


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
        rtu_connected=contract.RTU_CONNECTED,
    )
    assert n.rtu_connected == contract.RTU_CONNECTED
