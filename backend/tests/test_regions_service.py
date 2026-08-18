from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.regions_service import RegionsService


def _db_with_rows(rows: list) -> MagicMock:
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    return db


def test_list_cities_empty():
    assert RegionsService(_db_with_rows([])).list_cities() == []


def test_list_cities_skips_blank_and_leaves_abc_empty():
    rows = [
        SimpleNamespace(city_name="  ", region_name="Игнор"),
        SimpleNamespace(city_name=None, region_name="Игнор"),
        SimpleNamespace(city_name="Самара", region_name="Самарская область"),
        SimpleNamespace(city_name="  Москва  ", region_name="  Московская область  "),
        SimpleNamespace(city_name="Без региона", region_name=""),
    ]
    items = RegionsService(_db_with_rows(rows)).list_cities()
    assert [(i.abc, i.city_name, i.region_name) for i in items] == [
        (None, "Самара", "Самарская область"),
        (None, "Москва", "Московская область"),
        (None, "Без региона", None),
    ]
