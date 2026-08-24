"""Twilio parser / isolation unit tests (no live API)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from app.models.enums import ProviderCode, SyncJobType
from app.modules.sync_engine.progress import STAGE_DEFS
from app.modules.sync_engine.unified import PROVIDER_ORDER
from app.modules.twilio.persist import EmptyTwilioFetchError, persist_twilio_coverage
from app.providers.dto.common import ConnectionConfig
from app.providers.registry import get_provider
from app.providers.twilio import contract
from app.providers.twilio.parser import (
    build_catalog_rows,
    parse_country,
    parse_pricing,
    price_for_type,
    search_types,
)
from app.providers.twilio.provider import TwilioProvider


def test_search_types_only_from_subresource_uris():
    assert search_types(
        {
            "local": "/US/Local.json",
            "toll_free": "/US/TollFree.json",
            "unknown": "/US/X.json",
        }
    ) == ("local", "toll_free")
    assert search_types(None) == ()


def test_parse_country_and_pricing_map():
    country = parse_country(
        {
            "country": "United States",
            "country_code": "us",
            "beta": False,
            "subresource_uris": {
                "local": "/US/Local.json",
                "toll_free": "/US/TollFree.json",
                "voip": "/US/Voip.json",
            },
        }
    )
    assert country is not None
    assert country.country_iso == "US"
    assert country.types == ("local", "toll_free", "voip")

    prices = parse_pricing(
        {
            "iso_country": "US",
            "price_unit": "USD",
            "phone_number_prices": [
                {"number_type": "local", "current_price": "1.00", "base_price": "1.00"},
                {"number_type": "toll free", "current_price": "2.15", "base_price": "2.15"},
            ],
        }
    )
    assert price_for_type(prices, "local").current_price == Decimal("1.00")
    assert price_for_type(prices, "toll_free").current_price == Decimal("2.15")
    assert price_for_type(prices, "voip") is None

    rows = build_catalog_rows(
        [country],
        {
            "US": {
                "iso_country": "US",
                "price_unit": "USD",
                "phone_number_prices": [
                    {"number_type": "local", "current_price": "1.00"},
                    {"number_type": "toll free", "current_price": "2.15"},
                ],
            }
        },
    )
    by_type = {r.number_type: r for r in rows}
    assert by_type["local"].period_price == Decimal("1.00")
    assert by_type["local"].price_unit == "USD"
    assert by_type["voip"].period_price is None
    assert by_type["voip"].price_unit is None


def test_empty_pricing_payload_is_not_invented():
    assert parse_pricing({"url": None, "country": None, "phone_number_prices": None}) == {}


def test_persist_refuses_empty_countries():
    try:
        persist_twilio_coverage(
            _RefusingSession(),
            provider_id="11111111-1111-1111-1111-111111111111",
            job_id="22222222-2222-2222-2222-222222222222",
            countries=[],
            pricing_by_iso={},
            rows=[],
        )
        raise AssertionError("expected EmptyTwilioFetchError")
    except EmptyTwilioFetchError as exc:
        assert "0 countries" in exc.message


class _RefusingSession:
    def scalar(self, *_args, **_kwargs) -> int:
        return 7

    def execute(self, *_args, **_kwargs):  # pragma: no cover
        raise AssertionError("empty Twilio fetch must not delete rows")

    def add(self, *_args, **_kwargs):  # pragma: no cover
        raise AssertionError("empty Twilio fetch must not insert rows")

    def flush(self):  # pragma: no cover
        raise AssertionError("empty Twilio fetch must not flush")


def test_twilio_is_registered_but_outside_the_ru_pipeline():
    assert isinstance(get_provider(ProviderCode.twilio), TwilioProvider)
    assert ProviderCode.twilio not in PROVIDER_ORDER
    assert SyncJobType.twilio.value == "twilio"
    assert SyncJobType.twilio_numbers.value == "twilio_numbers"
    assert not [s for s in STAGE_DEFS if "twilio" in s["id"]]


def test_twilio_provider_refuses_ru_catalog_syncs():
    provider = TwilioProvider()
    conn = ConnectionConfig(
        base_url=contract.EXAMPLE_BASE_URL,
        auth_settings={"account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "auth_token": "token"},
    )
    for coro in (
        provider.sync_free_numbers(conn),
        provider.sync_purchased_numbers(conn),
        provider.sync_regions(conn),
        provider.sync_cities(conn),
    ):
        result = asyncio.run(coro)
        assert result.limitations
        assert not getattr(result, "numbers", None)


def test_search_type_paths_cover_openapi_keys():
    for key in (
        "local",
        "mobile",
        "toll_free",
        "voip",
        "national",
        "shared_cost",
        "machine_to_machine",
    ):
        assert key in contract.SEARCH_TYPE_PATHS


def test_contains_rotate_pattern_uses_sequence_wildcard():
    assert contract.contains_rotate_pattern(0) == "%00%"
    assert contract.contains_rotate_pattern(9) == "%09%"
    assert contract.contains_rotate_pattern(99) == "%99%"
    assert contract.contains_rotate_pattern(100) == "%00%"
    assert "*" not in contract.contains_rotate_pattern(12)


def test_region_grid_is_exactly_100_patterns():
    patterns = contract.contains_region_patterns()
    assert len(patterns) == 100
    assert patterns[0] == "%00%"
    assert patterns[-1] == "%99%"
    assert contract.geo_contains_queue(0) == ()
    assert contract.geo_contains_queue(1) == patterns
    assert contract.planned_request_total(896, 100) == 896 + 100 * 100


def test_region_search_keys_nanp_and_other():
    assert "DC" in contract.region_search_keys("US")
    assert "PR" not in contract.region_search_keys("US")
    assert "ON" in contract.region_search_keys("CA")
    assert contract.region_search_keys("GB") == (None,)


def test_available_search_params_gate_inregion_to_nanp():
    assert contract.available_search_params(
        country_iso="GB",
        in_region="ENG",
        area_code="20",
        contains="%00%",
    ) == {"Contains": "%00%"}
    assert contract.available_search_params(
        country_iso="US",
        in_region="AL",
        area_code="205",
    ) == {"InRegion": "AL", "AreaCode": "205"}


def test_cutover_does_not_delete_number_sync_rows():
    from sqlalchemy.dialects import postgresql

    from app.modules.twilio.persist import cutover_geo_snapshot

    captured: list[object] = []

    class _Capture:
        def execute(self, stmt):
            captured.append(stmt)

            class _Result:
                rowcount = 0

            return _Result()

        def flush(self):
            return None

    cutover_geo_snapshot(
        _Capture(),
        provider_id="11111111-1111-1111-1111-111111111111",
        job_id="22222222-2222-2222-2222-222222222222",
    )
    compiled = [stmt.compile(dialect=postgresql.dialect()) for stmt in captured]
    numbers = next(item for item in compiled if "twilio_available_numbers" in str(item))
    assert contract.NUMBER_SOURCE_GEO in numbers.params.values()
    assert contract.NUMBER_SOURCE_NUMBERS not in numbers.params.values()
    assert "source =" in str(numbers)


def test_geo_status_detail_uses_region_and_contains():
    from app.modules.twilio.runner import _geo_detail

    assert _geo_detail(78, 100, None, "%78%", 4) == "78 / 100 · %78% · 4 номеров"
    assert _geo_detail(78, 100, "AB", "%17%", 30) == "78 / 100 · AB · %17% · 30 номеров"
    assert _geo_detail(12, 51, "AL", None, 4) == "12 / 51 · AL · 4 номеров"


class _GeoStub:
    def __init__(self, locality: str | None = None, region_filter: str = "") -> None:
        self.locality = locality
        self.region_filter = region_filter


def test_build_number_cells_city_region_and_country_fallback():
    from app.modules.twilio.cells import build_number_cells, country_cell

    city = build_number_cells([_GeoStub("Calgary", "AB")])
    assert len(city) == 1
    assert city[0].locality == "Calgary"
    assert city[0].region_filter == "AB"

    region_only = build_number_cells([_GeoStub(None, "AL"), _GeoStub("", "")])
    assert len(region_only) == 1
    assert region_only[0].locality is None
    assert region_only[0].region_filter == "AL"

    assert build_number_cells([]) == [country_cell()]
    assert build_number_cells([_GeoStub("", ""), _GeoStub(None, "")]) == [country_cell()]
    assert len(build_number_cells([_GeoStub("Calgary", "AB"), _GeoStub("Calgary", "ab")])) == 1


def test_should_repeat_contains_at_ceiling():
    from app.modules.twilio.cells import should_repeat_contains

    assert should_repeat_contains(29, 29) is False
    assert should_repeat_contains(30, 1) is True
    assert should_repeat_contains(30, 0) is False
    assert should_repeat_contains(31, 5) is True


def test_country_cell_search_omits_inregion_and_inlocality():
    assert contract.available_search_params(
        country_iso="US",
        in_region=None,
        in_locality=None,
        contains="%78%",
    ) == {"Contains": "%78%"}
    assert contract.available_search_params(
        country_iso="GB",
        in_region="ENG",
        in_locality="London",
        contains="%00%",
    ) == {"InLocality": "London", "Contains": "%00%"}
    assert contract.available_search_params(
        country_iso="US",
        in_region="AL",
        in_locality="Birmingham",
        contains="%00%",
    ) == {"InRegion": "AL", "InLocality": "Birmingham", "Contains": "%00%"}


def test_cutover_numbers_row_scopes_to_own_country_type():
    from sqlalchemy.dialects import postgresql

    from app.modules.twilio.persist import cutover_numbers_row

    captured: list[object] = []

    class _Capture:
        def execute(self, stmt):
            captured.append(stmt)

            class _Result:
                rowcount = 2

            return _Result()

        def flush(self):
            return None

    deleted = cutover_numbers_row(
        _Capture(),
        provider_id="11111111-1111-1111-1111-111111111111",
        job_id="22222222-2222-2222-2222-222222222222",
        country_iso="GB",
        number_type="mobile",
    )
    assert deleted == 2
    compiled = captured[0].compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()
    assert "twilio_available_numbers" in sql
    assert "country_iso" in sql
    assert "number_type" in sql
    assert "last_sync_job_id" in sql
    assert "gb" in compiled.params.values() or "GB" in compiled.params.values()
    assert "mobile" in compiled.params.values()
    assert "source" not in sql


def test_ingest_upsert_does_not_steal_other_country_type():
    from sqlalchemy.dialects import postgresql

    from app.modules.twilio.persist import ingest_available_batch

    captured: list[object] = []

    class _Capture:
        def execute(self, stmt):
            captured.append(stmt)

    ingest_available_batch(
        _Capture(),
        provider_id="11111111-1111-1111-1111-111111111111",
        job_id="22222222-2222-2222-2222-222222222222",
        country_iso="US",
        country_name="United States",
        number_type="mobile",
        region_filter="",
        items=[{"phone_number": "+12025550100", "iso_country": "US"}],
        source=contract.NUMBER_SOURCE_NUMBERS,
    )
    compiled = [stmt.compile(dialect=postgresql.dialect()) for stmt in captured]
    numbers = next(item for item in compiled if "twilio_available_numbers" in str(item))
    sql = str(numbers).lower()
    assert "on conflict" in sql
    assert "country_iso" in sql
    assert "number_type" in sql
    assert numbers.params.get("number_type") == "mobile" or "mobile" in numbers.params.values()


def test_numbers_loaded_requires_matching_geo_job():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.modules.twilio.persist import catalog_numbers_loaded

    geo = uuid4()
    assert catalog_numbers_loaded(
        SimpleNamespace(numbers_sync_geo_job_id=geo, last_sync_job_id=geo)
    )
    assert not catalog_numbers_loaded(
        SimpleNamespace(numbers_sync_geo_job_id=geo, last_sync_job_id=uuid4())
    )
    assert not catalog_numbers_loaded(
        SimpleNamespace(numbers_sync_geo_job_id=None, last_sync_job_id=geo)
    )
    assert not catalog_numbers_loaded(
        SimpleNamespace(numbers_sync_geo_job_id=geo, last_sync_job_id=None)
    )


def test_fill_number_counts_uses_db_totals_not_stage():
    from app.modules.twilio.persist import fill_number_counts

    rows = [
        {"country_iso": "gb", "number_type": "mobile", "number_count": 0},
        {"country_iso": "US", "number_type": "local", "number_count": 3},
        {"country_iso": "DE", "number_type": "toll_free"},
    ]
    fill_number_counts(
        rows,
        {("GB", "mobile"): 12, ("US", "local"): 40},
    )
    assert rows[0]["number_count"] == 12
    assert rows[1]["number_count"] == 40
    assert rows[2]["number_count"] == 0


def test_ingest_numbers_staging_targets_stg_not_live_or_geo():
    from sqlalchemy.dialects import postgresql

    from app.models.twilio import TwilioAvailableNumber
    from app.modules.sync_engine.staging import staging_table_from_live
    from app.modules.twilio.persist import ingest_numbers_staging

    stg = staging_table_from_live(TwilioAvailableNumber.__table__, "twilio_available_numbers_stg")
    captured: list[object] = []

    class _Capture:
        def execute(self, stmt):
            captured.append(stmt)

    ingest_numbers_staging(
        _Capture(),
        stg,
        provider_id="11111111-1111-1111-1111-111111111111",
        job_id="22222222-2222-2222-2222-222222222222",
        country_iso="US",
        country_name="United States",
        number_type="mobile",
        items=[{"phone_number": "+12025550100", "iso_country": "US"}],
    )
    compiled = [stmt.compile(dialect=postgresql.dialect()) for stmt in captured]
    assert compiled
    joined = " ".join(str(item).lower() for item in compiled)
    assert "twilio_available_numbers_stg" in joined
    assert "twilio_geo" not in joined
    assert "into twilio_available_numbers " not in joined
    assert "on conflict" in joined


def test_cutover_from_staging_refuses_empty_when_live_has_rows():
    from app.modules.twilio.persist import EmptyTwilioFetchError, cutover_numbers_from_staging

    class _Session:
        def __init__(self) -> None:
            self.n = 0

        def scalar(self, _stmt):
            self.n += 1
            return 0 if self.n == 1 else 7

        def execute(self, *_args, **_kwargs):
            raise AssertionError("empty Twilio numbers fetch must not write live")

        def commit(self):
            raise AssertionError("empty Twilio numbers fetch must not commit")

        def flush(self):
            raise AssertionError("empty Twilio numbers fetch must not flush")

    try:
        cutover_numbers_from_staging(
            _Session(),
            provider_id="11111111-1111-1111-1111-111111111111",
            job_id="22222222-2222-2222-2222-222222222222",
            country_iso="GB",
            number_type="mobile",
            geo_job_id=None,
        )
        raise AssertionError("expected EmptyTwilioFetchError")
    except EmptyTwilioFetchError as exc:
        assert "0 numbers" in exc.message
        assert "7" in exc.message


def test_cutover_from_staging_empty_and_empty_is_noop():
    from app.modules.twilio.persist import cutover_numbers_from_staging

    executed: list[str] = []

    class _Session:
        def scalar(self, stmt):
            raw = str(stmt).lower()
            if "twilio_catalog" in raw:
                return None
            return 0

        def execute(self, stmt):
            executed.append(str(stmt).lower())

            class _Result:
                rowcount = 0

            return _Result()

        def commit(self):
            executed.append("commit")

        def flush(self):
            executed.append("flush")

    result = cutover_numbers_from_staging(
        _Session(),
        provider_id="11111111-1111-1111-1111-111111111111",
        job_id="22222222-2222-2222-2222-222222222222",
        country_iso="GB",
        number_type="mobile",
        geo_job_id=None,
    )
    assert result == {"incoming": 0, "previous": 0, "deleted": 0}
    assert any("truncate" in item for item in executed)
    assert any(item == "commit" for item in executed)
    assert not any("delete" in item and "twilio_available_numbers" in item for item in executed)
    assert not any("insert into twilio_available_numbers" in item for item in executed)


def test_cutover_insert_sql_preserves_first_seen_and_does_not_steal():
    from app.modules.twilio.persist import _cutover_insert_sql

    sql = _cutover_insert_sql().lower()
    set_part = sql.split("do update set", 1)[1]
    set_cols, where_part = set_part.split("where", 1)
    assert "first_seen_at" not in set_cols
    assert "created_at" not in set_cols
    assert "country_iso = excluded.country_iso" in where_part
    assert "number_type = excluded.number_type" in where_part
    assert "on conflict (provider_id, phone_number)" in sql


def test_attach_numbers_progress_keeps_this_run_count_while_running():
    from app.modules.twilio.persist import attach_numbers_progress_counts

    progress = {
        "target": {"country_iso": "GB", "number_type": "mobile"},
        "rows": [{"country_iso": "GB", "number_type": "mobile", "number_count": 12}],
        "summary": {"numbers_unique": 12},
    }
    out = attach_numbers_progress_counts(
        progress,
        running=True,
        counts={("GB", "mobile"): 40, ("US", "local"): 5},
    )
    assert out["rows"][0]["number_count"] == 12
    assert out["summary"]["numbers_unique"] == 17

    done = attach_numbers_progress_counts(
        progress,
        running=False,
        counts={("GB", "mobile"): 12, ("US", "local"): 5},
    )
    assert done["rows"][0]["number_count"] == 12
    assert done["summary"]["numbers_unique"] == 17


def test_numbers_status_detail_uses_pattern_repeat_cell_and_region():
    from app.modules.twilio.cells import NumberCell
    from app.modules.twilio.numbers_runner import _numbers_detail

    country = NumberCell(region_filter="", locality=None, label="")
    assert _numbers_detail(78, 1, 1, 1, country, "%78%", 4) == "78 / 1 / 1 / 1 · %78% · 4 номеров"
    assert _numbers_detail(0, 1, 1, 1, country, None, 0) == "0 / 1 / 1 / 1 · 0 номеров"
    region = NumberCell(region_filter="AB", locality="Calgary", label="Calgary")
    assert _numbers_detail(78, 1, 15, 98, region, "%78%", 4) == (
        "78 / 1 / 15 / 98 · AB · %78% · 4 номеров"
    )
    assert _numbers_detail(0, 1, 15, 98, region, None, 4) == "0 / 1 / 15 / 98 · AB · 4 номеров"
