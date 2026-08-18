from datetime import UTC, datetime
from uuid import uuid4

from app.models.enums import InventoryKind, MappingConfidence
from app.modules.sync_engine.persist import _catalog_row
from app.providers.dto.numbers import NormalizedNumber


def test_catalog_row_drops_provider_geo_keeps_external_ids():
    num = NormalizedNumber(
        inventory_kind=InventoryKind.free,
        provider_number_key="79001234567",
        msisdn="79001234567",
        city_external_id="city-1",
        region_external_id="region-1",
        city_name="Москва",
        region_name="Москва",
        buy_price=None,
        period_price=None,
        status_raw=None,
        mapping_confidence=MappingConfidence.high,
        normalized_payload={},
        raw_payload={},
    )
    row = _catalog_row(
        num,
        provider_id=uuid4(),
        job_id=uuid4(),
        inventory_kind=InventoryKind.free,
        table_name="sipout_free_numbers_raw",
        raw_id=None,
        loaded=datetime.now(UTC),
    )
    assert row["city_name"] is None
    assert row["region_name"] is None
    assert row["city_external_id"] == "city-1"
    assert row["region_external_id"] == "region-1"
    assert "mapping_confidence" not in row
    assert "number_type" not in row
    assert "mask" not in row
    assert "display_mask" not in row
    assert "points" not in row
    assert "notes" not in row
    assert "class" not in row
    assert "number_class" not in row
