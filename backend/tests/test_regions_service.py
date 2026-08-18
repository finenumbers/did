import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.errors import ProviderError
from app.services.regions_service import DirectoryRow, RegionsService, directory_rows_from_sipout


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


def test_directory_rows_from_sipout_joins_region_name():
    regions = [
        ParsedRegion(raw_payload={}, region_external_id="10", name="Самарская область"),
        ParsedRegion(raw_payload={}, region_external_id="20", name="  "),
    ]
    cities = [
        ParsedCity(raw_payload={}, city_external_id="1", name="Самара", region_external_id="10"),
        ParsedCity(raw_payload={}, city_external_id="2", name="  ", region_external_id="10"),
        ParsedCity(raw_payload={}, city_external_id="3", name="Без региона", region_external_id="20"),
        ParsedCity(
            raw_payload={},
            city_external_id="4",
            name="  Москва  ",
            region_external_id="99",
            region_name="Московская область",
        ),
    ]
    rows = directory_rows_from_sipout(regions, cities)
    assert rows == [
        DirectoryRow(
            city_name="Самара",
            region_name="Самарская область",
            city_external_id="1",
            region_external_id="10",
        ),
        DirectoryRow(
            city_name="Без региона",
            region_name=None,
            city_external_id="3",
            region_external_id="20",
        ),
        DirectoryRow(
            city_name="Москва",
            region_name=None,
            city_external_id="4",
            region_external_id="99",
        ),
    ]


def test_load_from_sipout_replaces_local_table():
    regions = [ParsedRegion(raw_payload={}, region_external_id="10", name="Самарская область")]
    cities = [
        ParsedCity(raw_payload={}, city_external_id="1", name="Самара", region_external_id="10"),
    ]
    client = MagicMock()
    client.get_cities = AsyncMock(return_value=object())
    provider = SimpleNamespace(
        connection=SimpleNamespace(
            base_url="https://lk.sipout.net/userapi/",
            auth_settings={"key": "k"},
            extra_settings={},
        )
    )
    db = MagicMock()
    db.scalar.return_value = provider
    added: list = []
    db.add_all.side_effect = added.extend

    with (
        patch("app.services.regions_service.SipOutClient", return_value=client),
        patch("app.services.regions_service.parse_geo", return_value=(regions, cities)),
    ):
        out = asyncio.run(RegionsService(db).load_from_sipout())

    assert out.ok is True
    assert out.count == 1
    db.execute.assert_called_once()
    db.add_all.assert_called_once()
    db.commit.assert_called_once()
    client.get_cities.assert_awaited_once()
    assert len(added) == 1
    assert added[0].city_name == "Самара"
    assert added[0].region_name == "Самарская область"
    assert added[0].abc is None


def test_load_from_sipout_requires_connection():
    db = MagicMock()
    db.scalar.return_value = SimpleNamespace(connection=None)
    with pytest.raises(ProviderError) as exc:
        asyncio.run(RegionsService(db).load_from_sipout())
    assert exc.value.code == "SIPOUT_NOT_CONFIGURED"
