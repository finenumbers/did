"""DIDWW parser / pagination / isolation unit tests (no live API)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from app.models.enums import ProviderCode, SyncJobType
from app.modules.didww.persist import EmptyDidwwFetchError, persist_didww_coverage
from app.modules.sync_engine.progress import STAGE_DEFS
from app.modules.sync_engine.unified import PROVIDER_ORDER
from app.providers.didww import contract
from app.providers.didww.client import DidwwClient
from app.providers.didww.parser import (
    SkuRow,
    collection_items,
    included_index,
    last_page_number,
    parse_did_group,
    pick_display_sku,
    total_records,
)
from app.providers.didww.provider import DidwwProvider
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderError
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


class ScriptedDidwwClient(DidwwClient):
    """Serves canned JSON:API pages; records the query params of every request."""

    def __init__(self, pages: list[dict[str, Any]]):
        super().__init__(
            ConnectionConfig(
                base_url=contract.EXAMPLE_BASE_URL,
                auth_settings={contract.AUTH_API_KEY: "test-key"},
            )
        )
        self._pages = list(pages)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _throttle(self) -> None:  # type: ignore[override]
        return None

    async def _get(  # type: ignore[override]
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((path, dict(params or {})))
        index = len(self.calls) - 1
        return self._pages[index] if index < len(self._pages) else {"data": []}


def _rows(start: int, count: int) -> list[dict[str, Any]]:
    return [
        {"id": f"grp-{i}", "type": contract.TYPE_DID_GROUPS, "attributes": {}}
        for i in range(start, start + count)
    ]


def _page(rows: list[dict[str, Any]], total: int | None, *, last: int = 3) -> dict[str, Any]:
    """DIDWW never sends links.next — only first/last."""
    payload: dict[str, Any] = {
        "data": rows,
        "links": {
            "first": "https://api.didww.com/v3/did_groups?page%5Bnumber%5D=1",
            "last": f"https://api.didww.com/v3/did_groups?page%5Bnumber%5D={last}",
        },
    }
    if total is not None:
        payload["meta"] = {"total_records": total, "api_version": contract.API_VERSION}
    return payload


def test_pagination_follows_total_records_without_links_next():
    client = ScriptedDidwwClient(
        [_page(_rows(0, 100), 250), _page(_rows(100, 100), 250), _page(_rows(200, 50), 250)]
    )
    items, _idx = asyncio.run(client.list_did_groups())

    assert len(items) == 250
    assert len(client.calls) == 3
    assert [call[1]["page[number]"] for call in client.calls] == [1, 2, 3]
    assert client.calls[0][1]["page[size]"] == contract.DID_GROUPS_PAGE_SIZE
    # Stable server-side order plus the in-stock filter and includes.
    assert client.calls[0][1]["sort"] == contract.SORT_DID_GROUPS
    assert client.calls[0][1][contract.FILTER_IN_STOCK] == "true"
    assert client.calls[0][1]["include"] == contract.DID_GROUPS_INCLUDE


def test_pagination_gate_fails_on_short_walk():
    client = ScriptedDidwwClient(
        [
            _page(_rows(0, 100), 250, last=3),
            _page(_rows(100, 30), 250, last=3),
            {"data": []},
        ]
    )

    with pytest.raises(ProviderError) as exc:
        asyncio.run(client.list_did_groups())

    assert exc.value.code == "DIDWW_SLICE_INCOMPLETE"
    assert exc.value.details["fetched"] == 130
    assert exc.value.details["total_records"] == 250
    assert len(client.calls) == 3


def test_pagination_keeps_going_past_links_last_when_short():
    client = ScriptedDidwwClient(
        [
            _page(_rows(0, 100), 180, last=2),
            _page(_rows(100, 56), 180, last=2),
            _page(_rows(156, 24), 180, last=3),
        ]
    )
    items, _idx = asyncio.run(client.list_did_groups())

    assert len(items) == 180
    assert [call[1]["page[number]"] for call in client.calls] == [1, 2, 3]


def test_did_groups_walks_countries_first():
    client = ScriptedDidwwClient(
        [
            _page(_rows(0, 80), 80, last=1),
            _page(_rows(80, 70), 70, last=1),
        ]
    )
    items, _idx = asyncio.run(client.list_did_groups(country_ids=["c-a", "c-b"]))

    assert len(items) == 150
    assert client.calls[0][1][contract.FILTER_COUNTRY_ID] == "c-a"
    assert client.calls[1][1][contract.FILTER_COUNTRY_ID] == "c-b"


def test_country_did_groups_merges_second_pass_when_meta_is_ahead():
    client = ScriptedDidwwClient(
        [
            _page(_rows(0, 100), 180, last=3),
            _page(_rows(100, 66), 180, last=3),
            {"data": []},
            _page(_rows(160, 20), 180, last=4),
            {"data": []},
        ]
    )
    items, _idx = asyncio.run(client.list_did_groups(country_ids=["c-1"]))

    assert len(items) == 180
    assert client.calls[3][1]["page[size]"] == 50


def test_pagination_continues_after_short_page_when_total_known():
    client = ScriptedDidwwClient(
        [
            _page(_rows(0, 100), 180, last=3),
            _page(_rows(100, 30), 180, last=3),
            _page(_rows(130, 50), 180, last=3),
        ]
    )
    items, _idx = asyncio.run(client.list_did_groups())

    assert len(items) == 180
    assert [call[1]["page[number]"] for call in client.calls] == [1, 2, 3]


def test_pagination_uses_latest_total_records():
    client = ScriptedDidwwClient(
        [
            _page(_rows(0, 100), 180, last=3),
            _page(_rows(100, 60), 160, last=2),
        ]
    )
    items, _idx = asyncio.run(client.list_did_groups())

    assert len(items) == 160
    assert len(client.calls) == 2


def test_last_page_number_reads_links_last():
    assert last_page_number({"links": {"last": "https://api.didww.com/v3/did_groups?page%5Bnumber%5D=57&page%5Bsize%5D=100"}}) == 57
    assert last_page_number({"links": {}}) is None
    assert last_page_number({}) is None


def test_pagination_stops_on_partial_page_without_meta():
    client = ScriptedDidwwClient([_page(_rows(0, 1000), None), _page(_rows(1000, 400), None)])
    items, _idx = asyncio.run(client.list_cities())

    assert len(items) == 1400
    assert len(client.calls) == 2
    assert client.calls[0][1]["page[size]"] == contract.CITIES_PAGE_SIZE


def test_pagination_deduplicates_repeated_resources():
    client = ScriptedDidwwClient(
        [_page(_rows(0, 100), 150), _page(_rows(50, 100), 150), _page(_rows(150, 0), 150)]
    )
    items, _idx = asyncio.run(client.list_did_groups())

    assert len(items) == 150
    assert len({row["id"] for row in items}) == 150


def test_unpaginated_collections_skip_page_params():
    client = ScriptedDidwwClient([{"data": [{"id": "c-1", "type": contract.TYPE_COUNTRIES}]}])
    asyncio.run(client.list_countries())

    path, params = client.calls[0]
    assert path == contract.PATH_COUNTRIES
    assert "page[size]" not in params and "page[number]" not in params
    assert contract.PATH_COUNTRIES in contract.UNPAGINATED_PATHS
    assert contract.PATH_REGIONS in contract.UNPAGINATED_PATHS


def test_unpaginated_collection_switches_to_paging_when_meta_reports_more():
    """If a "pagination disabled" endpoint ever truncates, page it instead of truncating."""
    client = ScriptedDidwwClient(
        [
            _page(_rows(0, 50), 120),
            _page(_rows(0, 100), 120),
            _page(_rows(100, 20), 120),
        ]
    )
    items, _idx = asyncio.run(client.list_regions())

    assert len(items) == 120
    assert "page[number]" not in client.calls[0][1]
    assert client.calls[1][1]["page[size]"] == contract.MAX_PAGE_SIZE
    assert [call[1].get("page[number]") for call in client.calls] == [None, 1, 2]


def test_total_records_reads_both_meta_keys():
    assert total_records({"meta": {"total_records": 7}}) == 7
    assert total_records({"meta": {"total_count": 361188}}) == 361188
    assert total_records({"data": []}) is None


def test_available_dids_requires_a_filter():
    client = ScriptedDidwwClient([{"data": []}])

    with pytest.raises(ProviderError) as exc:
        asyncio.run(client.list_available_dids())
    assert exc.value.code == "DIDWW_AVAILABLE_DIDS_FILTER_REQUIRED"
    assert not client.calls

    asyncio.run(client.list_available_dids(did_group_id="grp-1"))
    _path, params = client.calls[0]
    assert params[contract.FILTER_AVAILABLE_DID_GROUP] == "grp-1"


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

    def scalar(self, *_args, **_kwargs) -> int:
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
        "buy_price": ["0.3"],
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
    for column in ("country_name", "buy_price", "number_select", "channels_included", "voice_in"):
        service.list_facets(column=column, filters=filters, q="lond", value_q="lo")

    country_facet_sql = db.sql[2]
    assert "didww_catalog.country_iso IN ('GB')" in country_facet_sql
    # Exact amount, not round(): DIDWW prices are fractions of a unit.
    assert "didww_catalog.buy_price IN (0.3)" in country_facet_sql
    assert "round(" not in country_facet_sql

    price_facet_sql = db.sql[3]
    assert "didww_catalog.buy_price IN (0.3)" not in price_facet_sql
    assert "didww_catalog.country_iso IN ('GB')" in price_facet_sql

    with pytest.raises(ValueError):
        service.list_facets(column="skus_json", filters={}, q=None)


def test_didww_prices_keep_their_decimals():
    from app.services.didww_service import format_didww_price

    assert format_didww_price(Decimal("0.3000")) == "0.3"
    assert format_didww_price(Decimal("1.5000")) == "1.5"
    assert format_didww_price(Decimal("0.0000")) == "0"
    assert format_didww_price(Decimal("12.0000")) == "12"
    assert format_didww_price(Decimal("1500.0000")) == "1 500"
    assert format_didww_price(None) == ""


def test_features_has_membership_is_token_exact():
    from app.services.didww_service import features_has

    assert features_has("voice_in, sms_in", "voice_in") is True
    assert features_has("voice_in, sms_in", "sms_in") is True
    assert features_has("voice_in, sms_in", "voice_out") is False
    assert features_has("voice_out", "voice_in") is False
    assert features_has("voice_in,sms_in", "sms_in") is True
    assert features_has(None, "voice_in") is False
    assert features_has("", "t38") is False


def test_feature_flag_filter_compiles_to_features_like():
    from app.services.didww_service import DidwwCatalogService

    db = _CompilingSession()
    service = DidwwCatalogService(db)
    service.list_groups(
        page=1,
        page_size=50,
        sort_by="country_name",
        sort_dir="asc",
        filters={"voice_in": ["да"], "voice_out": ["нет"]},
        q=None,
    )
    sql = db.sql[0]
    assert "didww_catalog.features" in sql
    assert "%,voice_in,%" in sql
    assert "%,voice_out,%" in sql
    assert "didww_catalog.voice_in" not in sql


def test_features_text_is_not_a_facet_column():
    from app.services.didww_service import DidwwCatalogService

    service = DidwwCatalogService(_CompilingSession())
    with pytest.raises(ValueError):
        service.list_facets(column="features", filters={}, q=None)


def test_parse_filters_accepts_json_and_rejects_garbage():
    from app.services.didww_service import DidwwCatalogService

    assert DidwwCatalogService.parse_filters(None) == {}
    assert DidwwCatalogService.parse_filters('{"country_iso":["GB"]}') == {"country_iso": ["GB"]}
    assert DidwwCatalogService.parse_filters('{"country_iso":"GB"}') == {"country_iso": ["GB"]}
    with pytest.raises(ValueError):
        DidwwCatalogService.parse_filters("not-json")


def test_failed_sync_marks_the_running_stage():
    from app.models.sync import SyncJob
    from app.modules.didww.runner import _fail_current_stage, _progress_template, _set_stage

    job = SyncJob(stats={"progress": _progress_template()})
    _set_stage(job, "groups", "running", "100 из 250 групп")
    _fail_current_stage(job, "DIDWW slice incomplete did_groups")

    stages = {s["id"]: s for s in job.stats["progress"]["stages"]}
    assert stages["groups"]["status"] == "failed"
    assert stages["groups"]["detail"] == "DIDWW slice incomplete did_groups"
    assert stages["cutover"]["status"] == "pending"


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
