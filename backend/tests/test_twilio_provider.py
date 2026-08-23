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


def test_geo_status_detail_shows_planned_steps():
    from app.modules.twilio.runner import _first_pass_detail, _grid_detail

    assert _first_pass_detail(12, 51, "AL", 4) == "12 / 51, AL · 4 номеров"
    assert _first_pass_detail(1, 1, None, 0) == "1 / 1 · 0 номеров"
    assert _grid_detail(78, 100, "%78%", 4) == "78 / 100, %78% · 4 номеров"
