from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.providers.finenumbers.contract import OPERATOR_NOT_IN_REGISTRY
from app.providers.msisdn_split import DIGIT_CAPACITY_DEFAULT, split_msisdn, split_msisdn_by_capacity
from app.schemas.regions import RegionCapacitySaveItem
from app.services.regions_service import RegionsService, catalog_region_pair


def _db_with_rows(rows: list) -> MagicMock:
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    return db


def test_catalog_region_pair_keeps_real_geo():
    assert catalog_region_pair("  Самара  ", "  Самарская область  ") == (
        "Самара",
        "Самарская область",
    )
    assert catalog_region_pair("Казань", "") == ("Казань", None)
    assert catalog_region_pair("Казань", None) == ("Казань", None)


def test_catalog_region_pair_drops_blank_and_sentinel():
    assert catalog_region_pair("  ", "Игнор") is None
    assert catalog_region_pair(None, "Игнор") is None
    assert catalog_region_pair(OPERATOR_NOT_IN_REGISTRY, OPERATOR_NOT_IN_REGISTRY) is None
    assert catalog_region_pair("Казань", OPERATOR_NOT_IN_REGISTRY) is None
    assert catalog_region_pair(OPERATOR_NOT_IN_REGISTRY, "Татарстан") is None
    blob = (
        "Республика Адыгея, Республика Башкортостан, Республика Бурятия, "
        "Город Байконур, Херсонская область"
    )
    assert catalog_region_pair(blob, blob) is None
    assert catalog_region_pair("Майкоп", blob) == ("Майкоп", None)


def test_list_cities_empty():
    assert RegionsService(_db_with_rows([])).list_cities() == []


def test_list_cities_uses_stored_digit_capacity():
    samara_id = uuid4()
    moscow_id = uuid4()
    perm_id = uuid4()
    rows = [
        SimpleNamespace(id=uuid4(), city_name="  ", region_name="Игнор", digit_capacity=7),
        SimpleNamespace(
            id=samara_id,
            city_name="Самара",
            region_name="Самарская область",
            digit_capacity=6,
        ),
        SimpleNamespace(
            id=moscow_id,
            city_name="  Москва  ",
            region_name="  Московская область  ",
            digit_capacity=7,
        ),
        SimpleNamespace(id=perm_id, city_name="Без региона", region_name="", digit_capacity=5),
        SimpleNamespace(
            id=uuid4(),
            city_name=OPERATOR_NOT_IN_REGISTRY,
            region_name=OPERATOR_NOT_IN_REGISTRY,
            digit_capacity=7,
        ),
    ]
    items = RegionsService(_db_with_rows(rows)).list_cities()
    assert [(i.id, i.digit_capacity, i.city_name, i.region_name) for i in items] == [
        (samara_id, 6, "Самара", "Самарская область"),
        (moscow_id, 7, "Москва", "Московская область"),
        (perm_id, 5, "Без региона", None),
    ]


def test_load_from_catalog_rebuilds_keeps_capacity_deletes_stale():
    blob = (
        "Республика Адыгея, Республика Башкортостан, Республика Бурятия, "
        "Город Байконур, Херсонская область"
    )
    existing_samara = SimpleNamespace(
        city_name="Самара", region_name="Самарская область", digit_capacity=6
    )
    existing_blob = SimpleNamespace(city_name=blob, region_name=blob, digit_capacity=7)
    existing_gone = SimpleNamespace(
        city_name="Старый город", region_name="Старый регион", digit_capacity=6
    )
    db = MagicMock()
    db.execute.return_value.all.return_value = [
        ("Самара", "Самарская область"),
        ("Москва", "Москва"),
        (OPERATOR_NOT_IN_REGISTRY, OPERATOR_NOT_IN_REGISTRY),
        ("Казань", OPERATOR_NOT_IN_REGISTRY),
        ("Пермь", None),
        (blob, blob),
    ]
    db.scalars.return_value.all.return_value = [
        existing_samara,
        existing_blob,
        existing_gone,
    ]
    added: list = []
    deleted: list = []
    db.add_all.side_effect = added.extend
    db.delete.side_effect = deleted.append

    out = RegionsService(db).load_from_catalog()

    assert out.ok is True
    assert out.count == 2
    assert "удалено: 2" in out.message
    assert {(row.city_name, row.region_name, row.digit_capacity) for row in added} == {
        ("Москва", "Москва", DIGIT_CAPACITY_DEFAULT),
        ("Пермь", None, DIGIT_CAPACITY_DEFAULT),
    }
    assert existing_blob in deleted
    assert existing_gone in deleted
    assert existing_samara not in deleted
    db.add_all.assert_called_once()
    db.commit.assert_called_once()


def test_save_capacities_updates_found_rows():
    row_id = uuid4()
    row = SimpleNamespace(id=row_id, digit_capacity=7)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    out = RegionsService(db).save_capacities(
        [RegionCapacitySaveItem(id=row_id, digit_capacity=6)]
    )
    assert out.ok is True
    assert out.count == 1
    assert row.digit_capacity == 6
    db.commit.assert_called_once()


def test_save_capacities_rejects_unknown_id():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with pytest.raises(ValueError, match="не найдена"):
        RegionsService(db).save_capacities(
            [RegionCapacitySaveItem(id=uuid4(), digit_capacity=6)]
        )


def test_save_item_rejects_out_of_range_capacity():
    with pytest.raises(ValidationError):
        RegionCapacitySaveItem(id=uuid4(), digit_capacity=4)
    with pytest.raises(ValidationError):
        RegionCapacitySaveItem(id=uuid4(), digit_capacity=8)


def test_split_msisdn_default_is_three_plus_seven():
    assert split_msisdn("73833999999") == ("383", "3999999")
    assert split_msisdn("not-a-number") == (None, None)


def test_split_msisdn_by_capacity():
    assert split_msisdn_by_capacity("73833999999", 7) == ("383", "3999999")
    assert split_msisdn_by_capacity("73842399999", 6) == ("3842", "399999")
    assert split_msisdn_by_capacity("73842399999", 5) == ("38423", "99999")
    assert split_msisdn_by_capacity("73842399999", 4) is None
    assert split_msisdn_by_capacity("3842399999", 6) is None
