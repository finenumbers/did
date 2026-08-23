"""DIDWW parser / isolation unit tests (no live API)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.enums import ProviderCode, SyncJobType
from app.modules.didww.persist import EmptyDidwwFetchError, persist_didww_coverage
from app.modules.sync_engine.progress import STAGE_DEFS
from app.modules.sync_engine.unified import PROVIDER_ORDER
from app.providers.didww import contract
from app.providers.didww.parser import (
    SkuRow,
    collection_items,
    included_index,
    parse_did_group,
    pick_display_sku,
)
from app.providers.didww.provider import DidwwProvider
from app.providers.registry import get_provider


def _sku(sku_id: str, setup: str | None, monthly: str | None, channels: int) -> dict:
    return {
        "id": sku_id,
        "type": contract.TYPE_SKUS,
        "attributes": {
            "setup_price": setup,
            "monthly_price": monthly,
            "channels_included_count": channels,
        },
    }


def _did_groups_payload() -> dict:
    return {
        "data": [
            {
                "id": "grp-1",
                "type": contract.TYPE_DID_GROUPS,
                "attributes": {
                    "area_name": "London",
                    "prefix": "2035",
                    "features": ["voice_in", "sms_in"],
                    "is_metered": False,
                    "allow_additional_channels": True,
                    "service_restrictions": "none",
                },
                "meta": {
                    "needs_registration": True,
                    "is_available": True,
                    "available_dids_enabled": True,
                    "total_count": 42,
                },
                "relationships": {
                    "country": {"data": {"id": "c-1", "type": contract.TYPE_COUNTRIES}},
                    "region": {"data": {"id": "r-1", "type": contract.TYPE_REGIONS}},
                    "city": {"data": {"id": "ci-1", "type": contract.TYPE_CITIES}},
                    "did_group_type": {
                        "data": {"id": "t-1", "type": contract.TYPE_DID_GROUP_TYPES}
                    },
                    "stock_keeping_units": {
                        "data": [
                            {"id": "s-1", "type": contract.TYPE_SKUS},
                            {"id": "s-2", "type": contract.TYPE_SKUS},
                        ]
                    },
                },
            }
        ],
        "included": [
            {
                "id": "c-1",
                "type": contract.TYPE_COUNTRIES,
                "attributes": {"name": "United Kingdom", "iso": "GB", "prefix": "44"},
            },
            {
                "id": "r-1",
                "type": contract.TYPE_REGIONS,
                "attributes": {"name": "England"},
            },
            {
                "id": "ci-1",
                "type": contract.TYPE_CITIES,
                "attributes": {"name": "London"},
            },
            {
                "id": "t-1",
                "type": contract.TYPE_DID_GROUP_TYPES,
                "attributes": {"name": "Local"},
            },
            _sku("s-1", "5.00", "3.00", 2),
            _sku("s-2", "4.00", "2.00", 0),
        ],
    }


def test_parse_did_group_maps_attributes_meta_and_relations():
    payload = _did_groups_payload()
    rows = collection_items(payload)
    idx = included_index(payload)
    group = parse_did_group(rows[0], idx)

    assert group.group_id == "grp-1"
    assert group.country_name == "United Kingdom"
    assert group.country_iso == "GB"
    assert group.country_prefix == "44"
    assert group.region_name == "England"
    assert group.city_name == "London"
    assert group.prefix == "2035"
    assert group.did_type == "Local"
    assert group.features == ["voice_in", "sms_in"]
    assert group.is_metered is False
    assert group.needs_registration is True
    assert group.number_select is True
    assert group.stock_count == 42
    assert len(group.skus) == 2


def test_display_sku_prefers_zero_channels():
    payload = _did_groups_payload()
    group = parse_did_group(collection_items(payload)[0], included_index(payload))
    sku = pick_display_sku(group.skus)

    assert sku is not None
    assert sku.sku_id == "s-2"
    assert sku.channels_included == 0
    assert sku.monthly_price == Decimal("2.00")
    assert sku.setup_price == Decimal("4.00")


def test_display_sku_falls_back_to_cheapest_monthly():
    skus = [
        SkuRow(sku_id="a", setup_price=Decimal("1"), monthly_price=Decimal("9"), channels_included=2),
        SkuRow(sku_id="b", setup_price=Decimal("7"), monthly_price=Decimal("3"), channels_included=4),
    ]
    assert pick_display_sku(skus).sku_id == "b"
    assert pick_display_sku([]) is None


def test_parse_did_group_tolerates_missing_includes_and_meta():
    resource = {"id": "grp-2", "type": contract.TYPE_DID_GROUPS, "attributes": {}}
    group = parse_did_group(resource, {})

    assert group.group_id == "grp-2"
    assert group.country_name is None
    assert group.stock_count is None
    assert group.needs_registration is None
    assert group.skus == []


def test_empty_fetch_never_wipes_catalog():
    with pytest.raises(EmptyDidwwFetchError):
        persist_didww_coverage(
            _RefusingSession(),
            provider_id="11111111-1111-1111-1111-111111111111",
            job_id="22222222-2222-2222-2222-222222222222",
            countries=[],
            regions=[],
            cities=[],
            group_types=[],
            groups=[],
        )


class _RefusingSession:
    """Any write attempt during an empty fetch is a test failure."""

    def query(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def count(self) -> int:
        return 7

    def execute(self, *_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("empty DIDWW fetch must not delete rows")

    def add(self, *_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("empty DIDWW fetch must not insert rows")

    def flush(self):  # pragma: no cover - must not run
        raise AssertionError("empty DIDWW fetch must not flush")


class _CompilingSession:
    """Compiles statements against the postgres dialect instead of executing them."""

    class _Result(list):
        def all(self) -> list:
            return []

    def __init__(self) -> None:
        self.sql: list[str] = []

    def _record(self, stmt) -> None:
        from sqlalchemy.dialects import postgresql

        self.sql.append(
            str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        )

    def scalar(self, stmt) -> int:
        self._record(stmt)
        return 0

    def scalars(self, stmt):
        self._record(stmt)
        return self._Result()

    def execute(self, stmt):
        self._record(stmt)
        return self._Result()


def test_catalog_queries_compile_and_facets_exclude_their_own_column():
    from app.services.didww_service import DidwwCatalogService

    db = _CompilingSession()
    service = DidwwCatalogService(db)
    filters = {
        "country_iso": ["GB", "__empty__"],
        "buy_price": ["4"],
        "number_select": ["да"],
        "channels_included": ["0"],
    }

    service.list_groups(
        page=1,
        page_size=50,
        sort_by="country_name",
        sort_dir="asc",
        filters=filters,
        q="lond",
    )
    for column in ("country_name", "buy_price", "number_select", "channels_included", "features"):
        service.list_facets(column=column, filters=filters, q="lond", value_q="lo")

    country_facet_sql = db.sql[2]
    assert "didww_catalog.country_iso IN ('GB')" in country_facet_sql
    assert "round(didww_catalog.buy_price) IN (4)" in country_facet_sql

    price_facet_sql = db.sql[3]
    assert "round(didww_catalog.buy_price) IN (4)" not in price_facet_sql
    assert "didww_catalog.country_iso IN ('GB')" in price_facet_sql

    with pytest.raises(ValueError):
        service.list_facets(column="skus_json", filters={}, q=None)


def test_parse_filters_accepts_json_and_rejects_garbage():
    from app.services.didww_service import DidwwCatalogService

    assert DidwwCatalogService.parse_filters(None) == {}
    assert DidwwCatalogService.parse_filters('{"country_iso":["GB"]}') == {"country_iso": ["GB"]}
    assert DidwwCatalogService.parse_filters('{"country_iso":"GB"}') == {"country_iso": ["GB"]}
    with pytest.raises(ValueError):
        DidwwCatalogService.parse_filters("not-json")


def test_didww_is_registered_but_outside_the_ru_pipeline():
    assert isinstance(get_provider(ProviderCode.didww), DidwwProvider)
    assert ProviderCode.didww not in PROVIDER_ORDER
    assert SyncJobType.didww.value == "didww"
    assert not [s for s in STAGE_DEFS if "didww" in s["id"]]


def test_didww_provider_refuses_ru_catalog_syncs():
    import asyncio

    from app.providers.dto.common import ConnectionConfig

    provider = DidwwProvider()
    conn = ConnectionConfig(base_url=contract.EXAMPLE_BASE_URL, auth_settings={"api_key": "k"})
    for coro in (
        provider.sync_free_numbers(conn),
        provider.sync_purchased_numbers(conn),
        provider.sync_regions(conn),
        provider.sync_cities(conn),
    ):
        result = asyncio.run(coro)
        assert result.limitations
        assert not getattr(result, "numbers", None)
