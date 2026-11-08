"""MCN Telecom provider unit tests (no live API)."""

from __future__ import annotations

import asyncio

from app.models.enums import InventoryKind
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderError, ProviderTransportError
from app.providers.mcn import contract, mapper, parser
from app.providers.mcn.client import McnClient, auth_headers
from app.providers.mcn.provider import McnProvider


def _conn(*, mode: str | None = "bearer") -> ConnectionConfig:
    auth: dict = {"api_key": "test-token"}
    if mode:
        auth[contract.AUTH_HEADER_MODE] = mode
    return ConnectionConfig(base_url="https://shop.mcn.ru", auth_settings=auth)


def test_auth_headers_modes():
    assert auth_headers("t", contract.AUTH_MODE_BEARER)["Authorization"] == "Bearer t"
    assert auth_headers("t", contract.AUTH_MODE_RAW)["Authorization"] == "t"
    assert auth_headers("t", contract.AUTH_MODE_X_AUTH)["X-Auth-Token"] == "t"


def test_has_ru_country():
    assert parser.has_ru_country({"countries": [{"country_code": 643, "name": "RU"}]})
    assert not parser.has_ru_country({"countries": [{"country_code": 840}]})


def test_extract_numbers_page():
    body = {
        "totalNumbers": 3,
        "numbers": [
            {"number": "74951234567", "default_tariff": {"price_setup": 10, "price_per_period": 1}},
            {"number": "74951234568"},
        ],
    }
    items, total = parser.extract_numbers_page(body)
    assert total == 3
    assert len(items) == 2


def test_map_number_prices_and_msisdn():
    parsed = parser.parse_number_item(
        {
            "number": "74951234567",
            "city_id": 12,
            "region": 77,
            "ndc_type_id": "ABC",
            "beauty_level": 2,
            "default_tariff": {"price_setup": 100.5, "price_per_period": 45},
            "currency": "RUB",
        },
        city_name="Москва",
        region_name="Москва",
    )
    num = mapper.map_number(parsed, inventory_kind=InventoryKind.free)
    assert num is not None
    assert num.msisdn == "74951234567"
    assert num.provider_number_key == "74951234567"
    assert float(num.buy_price) == 100.5
    assert float(num.period_price) == 45
    assert num.city_name == "Москва"


def test_city_free_counts_filters_zero():
    rows = [
        {"city_id": 1, "free_numbers_count": 5, "city_name": "A", "region": {"name": "R"}},
        {"city_id": 2, "free_numbers_count": 0, "city_name": "B"},
        {"city_id": 3, "city_name": "C"},
    ]
    out = mapper.city_free_counts(rows)
    assert len(out) == 1
    assert out[0][0] == 1 and out[0][1] == 5


def test_iter_numbers_slice_completeness_fail():
    client = McnClient(_conn(), page_limit=2)

    async def fake_page(*, country_code=643, page_number=1, limit_per_page=None, city_id=None):
        if page_number == 1:
            return (
                [{"number": "74950000001"}],
                5,
                RawHttpResult(200, "{}", {}, {}, 1, "u"),
            )
        return ([], 5, RawHttpResult(200, "{}", {}, {}, 1, "u"))

    client.get_numbers_page = fake_page  # type: ignore[method-assign]

    async def run():
        try:
            await client.iter_numbers_slice(label="test")
            assert False, "expected incomplete"
        except ProviderError as exc:
            assert exc.code == "MCN_SLICE_INCOMPLETE"

    asyncio.run(run())


def test_iter_numbers_slice_full_pages():
    client = McnClient(_conn(), page_limit=2)

    async def fake_page(*, country_code=643, page_number=1, limit_per_page=None, city_id=None):
        all_nums = [{"number": f"7495000000{i}"} for i in range(1, 5)]
        start = (page_number - 1) * 2
        page = all_nums[start : start + 2]
        return (
            page,
            4,
            RawHttpResult(200, "{}", {}, {}, 1, "u"),
        )

    client.get_numbers_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, _envs, meta = await client.iter_numbers_slice(label="RU")
        assert len(items) == 4
        assert meta["total_numbers"] == 4

    asyncio.run(run())


def _raw() -> RawHttpResult:
    return RawHttpResult(200, "{}", {}, {}, 1, "u")


def test_iter_numbers_slice_progress_and_wave_order():
    client = McnClient(_conn(), page_limit=2)
    calls: list[int] = []

    async def fake_page(*, country_code=643, page_number=1, limit_per_page=None, city_id=None):
        calls.append(page_number)
        pages = {
            1: [{"number": "74950000001"}, {"number": "74950000002"}],
            2: [{"number": "74950000003"}, {"number": "74950000004"}],
            3: [{"number": "74950000005"}, {"number": "74950000006"}],
        }
        return pages[page_number], 6, _raw()

    client.get_numbers_page = fake_page  # type: ignore[method-assign]
    seen: list[tuple[int | None, int | None]] = []

    async def on_progress(detail, current=None, total=None):
        seen.append((current, total))

    async def run():
        items, _envs, meta = await client.iter_numbers_slice(label="RU", on_progress=on_progress)
        assert [item["number"] for item in items] == [f"7495000000{i}" for i in range(1, 7)]
        assert meta["total_numbers"] == 6
        assert calls == [1, 2, 3]
        assert (6, 6) in seen
        assert seen[-1] == (6, 6)

    asyncio.run(run())


def test_iter_numbers_slice_overlap_falls_back_to_sequential():
    client = McnClient(_conn(), page_limit=2)
    calls: list[int] = []

    async def fake_page(*, country_code=643, page_number=1, limit_per_page=None, city_id=None):
        calls.append(page_number)
        if page_number == 1:
            return [{"number": "74950000001"}, {"number": "74950000002"}], 6, _raw()
        if page_number == 2 and calls.count(2) == 1:
            return [{"number": "74950000002"}, {"number": "74950000003"}], 6, _raw()
        if page_number == 2:
            return [{"number": "74950000003"}, {"number": "74950000004"}], 6, _raw()
        if page_number == 3 and calls.count(3) == 1:
            return [{"number": "74950000005"}, {"number": "74950000006"}], 6, _raw()
        return [{"number": "74950000005"}, {"number": "74950000006"}], 6, _raw()

    client.get_numbers_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, _envs, _meta = await client.iter_numbers_slice(label="RU")
        assert [item["number"] for item in items] == [f"7495000000{i}" for i in range(1, 7)]
        assert calls == [1, 2, 3, 2, 3]

    asyncio.run(run())


def test_iter_numbers_slice_rate_limit_keeps_good_pages():
    client = McnClient(_conn(), page_limit=2)
    calls: list[int] = []

    async def fake_page(*, country_code=643, page_number=1, limit_per_page=None, city_id=None):
        calls.append(page_number)
        if page_number == 3 and calls.count(3) == 1:
            raise ProviderTransportError("MCN rate limited (429)", details={"status": 429})
        start = (page_number - 1) * 2
        page = [{"number": f"7495000000{i}"} for i in range(start + 1, start + 3)]
        return page, 8, _raw()

    client.get_numbers_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, _envs, _meta = await client.iter_numbers_slice(label="RU")
        assert [item["number"] for item in items] == [f"7495000000{i}" for i in range(1, 9)]
        assert calls == [1, 2, 3, 4, 3]

    asyncio.run(run())


def test_iter_numbers_slice_short_middle_page_is_incomplete():
    client = McnClient(_conn(), page_limit=2)
    calls: list[int] = []

    async def fake_page(*, country_code=643, page_number=1, limit_per_page=None, city_id=None):
        calls.append(page_number)
        if page_number == 1:
            return [{"number": "74950000001"}, {"number": "74950000002"}], 6, _raw()
        if page_number == 2:
            return [{"number": "74950000003"}], 6, _raw()
        return [{"number": "74950000005"}, {"number": "74950000006"}], 6, _raw()

    client.get_numbers_page = fake_page  # type: ignore[method-assign]

    async def run():
        try:
            await client.iter_numbers_slice(label="RU")
            assert False, "expected incomplete"
        except ProviderError as exc:
            assert exc.code == "MCN_SLICE_INCOMPLETE"
        assert calls.count(2) == 2

    asyncio.run(run())


def test_iter_numbers_slice_city_stays_sequential():
    client = McnClient(_conn(), page_limit=2)
    inflight = 0
    max_inflight = 0

    async def fake_page(*, country_code=643, page_number=1, limit_per_page=None, city_id=None):
        nonlocal inflight, max_inflight
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.01)
        inflight -= 1
        start = (page_number - 1) * 2
        page = [{"number": f"7495000000{i}"} for i in range(start + 1, start + 3)]
        if page_number > 2:
            page = []
        return page, 4, _raw()

    client.get_numbers_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, _envs, _meta = await client.iter_numbers_slice(city_id=7, label="city=7")
        assert len(items) == 4
        assert max_inflight == 1

    asyncio.run(run())


def test_iter_numbers_slice_seed_skips_first_page():
    client = McnClient(_conn(), page_limit=2)
    calls: list[int] = []

    async def fake_page(*, country_code=643, page_number=1, limit_per_page=None, city_id=None):
        calls.append(page_number)
        return [{"number": "74950000003"}, {"number": "74950000004"}], 4, _raw()

    client.get_numbers_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, envs, _meta = await client.iter_numbers_slice(
            label="RU",
            seed_items=[{"number": "74950000001"}, {"number": "74950000002"}],
            seed_total=4,
            seed_envelope=_raw(),
        )
        assert [item["number"] for item in items] == [f"7495000000{i}" for i in range(1, 5)]
        assert calls == [2]
        assert len(envs) == 2

    asyncio.run(run())


def test_provider_capabilities():
    caps = McnProvider().capabilities()
    assert caps["free_numbers"]["supported"] is True
    assert caps["purchased_numbers"]["supported"] is False
    assert caps["dictionaries"]["supported"] is True
