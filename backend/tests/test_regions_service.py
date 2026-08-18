from types import SimpleNamespace
from unittest.mock import MagicMock

from app.providers.finenumbers.contract import OPERATOR_NOT_IN_REGISTRY
from app.services.regions_service import (
    DIGIT_CAPACITY,
    RegionsService,
    catalog_region_pair,
)


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


def test_list_cities_empty():
    assert RegionsService(_db_with_rows([])).list_cities() == []


def test_list_cities_skips_blank_and_sets_digit_capacity():
    rows = [
        SimpleNamespace(city_name="  ", region_name="Игнор"),
        SimpleNamespace(city_name=None, region_name="Игнор"),
        SimpleNamespace(city_name="Самара", region_name="Самарская область"),
        SimpleNamespace(city_name="  Москва  ", region_name="  Московская область  "),
        SimpleNamespace(city_name="Без региона", region_name=""),
        SimpleNamespace(
            city_name=OPERATOR_NOT_IN_REGISTRY,
            region_name=OPERATOR_NOT_IN_REGISTRY,
        ),
    ]
    items = RegionsService(_db_with_rows(rows)).list_cities()
    assert [(i.digit_capacity, i.city_name, i.region_name) for i in items] == [
        (DIGIT_CAPACITY, "Самара", "Самарская область"),
        (DIGIT_CAPACITY, "Москва", "Московская область"),
        (DIGIT_CAPACITY, "Без региона", None),
    ]


def test_load_from_catalog_replaces_local_table():
    select_result = MagicMock()
    select_result.all.return_value = [
        ("Самара", "Самарская область"),
        ("Самара", "Самарская область"),
        ("  Москва  ", "Москва"),
        (OPERATOR_NOT_IN_REGISTRY, OPERATOR_NOT_IN_REGISTRY),
        ("", "Игнор"),
        ("Казань", OPERATOR_NOT_IN_REGISTRY),
        ("Пермь", None),
    ]
    db = MagicMock()
    db.execute.side_effect = [select_result, MagicMock()]
    added: list = []
    db.add_all.side_effect = added.extend

    out = RegionsService(db).load_from_catalog()

    assert out.ok is True
    assert out.count == 3
    assert {(row.city_name, row.region_name) for row in added} == {
        ("Самара", "Самарская область"),
        ("Москва", "Москва"),
        ("Пермь", None),
    }
    assert all(row.loaded_at is not None for row in added)
    assert db.execute.call_count == 2
    db.add_all.assert_called_once()
    db.commit.assert_called_once()
    assert "SipOut" not in out.message
