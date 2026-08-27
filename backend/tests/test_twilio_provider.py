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


def test_region_grid_is_exactly_100_patterns():
    patterns = contract.contains_region_patterns()
    assert len(patterns) == 100
    assert patterns[0] == "%00%"
    assert patterns[-1] == "%99%"


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


def test_cutover_deletes_all_stale_numbers_not_only_geo_sync():
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
    sql = str(numbers).lower()
    assert "source" not in sql
    assert "last_sync_job_id" in sql


def test_enrich_cells_nanp_local_uses_states_other_is_country():
    from app.modules.twilio.cells import country_cell, enrich_cells

    us_local = enrich_cells("US", "local")
    assert len(us_local) == len(contract.US_STATE_CODES)
    assert us_local[0].region_filter == "AL"
    assert us_local[0].locality is None

    ca_local = enrich_cells("CA", "local")
    assert len(ca_local) == len(contract.CA_PROVINCE_CODES)
    assert {cell.region_filter for cell in ca_local} == set(contract.CA_PROVINCE_CODES)

    assert enrich_cells("US", "toll_free") == [country_cell()]
    assert enrich_cells("GB", "local") == [country_cell()]


def test_should_repeat_pattern_needs_two_empty_streak():
    from app.modules.twilio.cells import apply_batch_novelty, should_repeat_pattern

    assert should_repeat_pattern(29, 0) is False
    assert should_repeat_pattern(30, 0) is True
    assert should_repeat_pattern(30, 1) is True
    assert should_repeat_pattern(30, 2) is False
    assert should_repeat_pattern(31, 1) is True

    phones: set[str] = set()
    regions: set[str] = set()
    cities: set[str] = set()
    first = apply_batch_novelty(
        [{"phone_number": "+12025550100", "region": "CA", "locality": "Oakland"}],
        phones,
        regions,
        cities,
    )
    assert first >= 1
    assert apply_batch_novelty(
        [{"phone_number": "+12025550100", "region": "CA", "locality": "Oakland"}],
        phones,
        regions,
        cities,
    ) == 0


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


def test_coverage_owner_uses_catalog_not_payload():
    from app.providers.twilio.parser import coverage_owner

    assert coverage_owner(country_iso="ar", country_name=" Argentina ", number_type="toll_free") == (
        "AR",
        "Argentina",
        "toll_free",
    )
    assert coverage_owner(country_iso="US", country_name="", number_type=" local ") == (
        "US",
        None,
        "local",
    )


def test_ingest_keeps_catalog_iso_when_payload_is_us():
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
        country_iso="AR",
        country_name="Argentina",
        number_type="toll_free",
        region_filter="",
        items=[{"phone_number": "+18005550100", "iso_country": "US"}],
        source=contract.NUMBER_SOURCE_NUMBERS,
    )
    compiled = [stmt.compile(dialect=postgresql.dialect()) for stmt in captured]
    numbers = next(item for item in compiled if "twilio_available_numbers" in str(item))
    params = numbers.params
    assert params.get("country_iso") == "AR"
    assert params.get("country_name") == "Argentina"
    assert params.get("number_type") == "toll_free"
    assert "US" not in {params.get("country_iso"), params.get("country_name")}


def test_realign_sql_joins_catalog_name_and_type():
    from sqlalchemy.dialects import postgresql

    from app.modules.twilio.persist import realign_available_number_iso

    captured: list[object] = []

    class _Capture:
        def execute(self, stmt, params=None):
            captured.append((stmt, params))

            class _Result:
                rowcount = 4

            return _Result()

        def flush(self):
            return None

    out = realign_available_number_iso(
        _Capture(),
        provider_id="11111111-1111-1111-1111-111111111111",
    )
    assert out["realigned"] == 4
    stmt, params = captured[0]
    sql = str(stmt).lower()
    compiled = stmt.compile(dialect=postgresql.dialect()) if hasattr(stmt, "compile") else None
    text_sql = str(compiled) if compiled is not None else sql
    lowered = text_sql.lower()
    assert "twilio_catalog" in lowered
    assert "country_name" in lowered
    assert "number_type" in lowered
    assert "is distinct from" in lowered
    assert params is None or params.get("provider_id") or getattr(compiled, "params", {}).get(
        "provider_id"
    )


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


def test_cutover_numbers_row_scopes_and_refuses_empty():
    from sqlalchemy.dialects import postgresql

    from app.modules.twilio.persist import EmptyTwilioFetchError, cutover_numbers_row

    class _EmptyLive:
        def __init__(self, previous: int, incoming: int):
            self.previous = previous
            self.incoming = incoming
            self.n = 0

        def scalar(self, _stmt):
            self.n += 1
            return self.incoming if self.n == 2 else self.previous

        def execute(self, *_args, **_kwargs):
            raise AssertionError("empty Twilio numbers fetch must not wipe the row")

        def flush(self):
            raise AssertionError("empty Twilio numbers fetch must not flush")

    try:
        cutover_numbers_row(
            _EmptyLive(7, 0),
            provider_id="11111111-1111-1111-1111-111111111111",
            job_id="22222222-2222-2222-2222-222222222222",
            country_iso="GB",
            number_type="mobile",
        )
        raise AssertionError("expected EmptyTwilioFetchError")
    except EmptyTwilioFetchError as exc:
        assert "0 numbers" in exc.message
        assert "7" in exc.message

    captured: list[object] = []

    class _Capture:
        def scalar(self, _stmt):
            if getattr(self, "n", 0) == 0:
                self.n = 1
                return 5
            return 3

        def execute(self, stmt):
            captured.append(stmt)

            class _Result:
                rowcount = 2

            return _Result()

        def flush(self):
            return None

    result = cutover_numbers_row(
        _Capture(),
        provider_id="11111111-1111-1111-1111-111111111111",
        job_id="22222222-2222-2222-2222-222222222222",
        country_iso="GB",
        number_type="mobile",
    )
    assert result["incoming"] == 3
    assert result["previous"] == 5
    assert result["numbers_deleted"] == 2
    compiled = [stmt.compile(dialect=postgresql.dialect()) for stmt in captured]
    numbers = next(item for item in compiled if "twilio_available_numbers" in str(item))
    sql = str(numbers).lower()
    assert "country_iso" in sql
    assert "number_type" in sql
    assert "last_sync_job_id" in sql
    assert "source" not in sql


def test_numbers_job_outcome_fails_only_when_all_rows_failed():
    from app.models.enums import SyncJobStatus
    from app.modules.twilio.numbers_runner import numbers_job_outcome

    assert numbers_job_outcome(0, 3) == SyncJobStatus.success
    assert numbers_job_outcome(1, 3) == SyncJobStatus.success
    assert numbers_job_outcome(3, 3) == SyncJobStatus.failed
    assert numbers_job_outcome(0, 0) == SyncJobStatus.success


def test_progress_with_db_counts_preserves_live_on_running_countries():
    from app.api.routes.twilio import _progress_with_db_counts

    progress = {
        "rows": [{"country_iso": "GB", "number_type": "mobile", "number_count": 7}],
        "summary": {"numbers_unique": 7},
    }

    class _Boom:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("running countries must not overwrite live counts from DB")

    kept = _progress_with_db_counts(progress, _Boom(), "ignored", preserve_live_counts=True)
    assert kept is progress
    assert kept["rows"][0]["number_count"] == 7


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
    assert _numbers_detail(3, 2, 1, 1, country, "%02%", 4) == "3 / 2 - %02%"
    assert _numbers_detail(0, 1, 1, 1, country, None, 0) == "0 / 1"
    region = NumberCell(region_filter="TX", locality="Austin", label="TX")
    assert _numbers_detail(3, 2, 15, 98, region, "%02%", 4) == "3 / 2 - %02% - TX"
    assert _numbers_detail(0, 1, 15, 98, region, None, 4) == "0 / 1 - TX"


def test_reclaim_stale_jobs_only_when_lock_free():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.models.enums import SyncJobStatus
    from app.modules.twilio.runner import STALE_JOB_MESSAGE, reclaim_stale_twilio_jobs

    now = datetime.now(timezone.utc)

    class _Job:
        def __init__(self, status, *, created_at=None):
            self.status = status
            self.error_summary = None
            self.finished_at = None
            self.created_at = created_at

    class _Session:
        def __init__(self, jobs):
            self.jobs = jobs
            self.committed = False

        def scalars(self, _stmt):
            return SimpleNamespace(all=lambda: self.jobs)

        def commit(self):
            self.committed = True

    running = _Job(SyncJobStatus.running)
    held = _Session([running])
    assert reclaim_stale_twilio_jobs(held, lock_free=False) == 0
    assert running.status == SyncJobStatus.running
    assert held.committed is False

    stale_running = _Job(SyncJobStatus.running)
    free = _Session([stale_running])
    assert reclaim_stale_twilio_jobs(free, lock_free=True) == 1
    assert stale_running.status == SyncJobStatus.failed
    assert stale_running.error_summary == STALE_JOB_MESSAGE
    assert free.committed is True

    young = _Job(SyncJobStatus.pending, created_at=now - timedelta(seconds=5))
    young_session = _Session([young])
    assert reclaim_stale_twilio_jobs(young_session, lock_free=True) == 0
    assert young.status == SyncJobStatus.pending
    assert young_session.committed is False

    old = _Job(SyncJobStatus.pending, created_at=now - timedelta(seconds=61))
    old_session = _Session([old])
    assert reclaim_stale_twilio_jobs(old_session, lock_free=True) == 1
    assert old.status == SyncJobStatus.failed
    assert old_session.committed is True


def test_search_or_empty_raises_429_treats_404_as_empty():
    from app.modules.twilio.runner import _search_or_empty
    from app.providers.errors import ProviderError

    class _Client:
        def __init__(self, exc: ProviderError):
            self.exc = exc

        async def search_available(self, **_kwargs):
            raise self.exc

    async def _run_429():
        try:
            await _search_or_empty(
                _Client(ProviderError("throttled", details={"status": 429})),
                country_iso="US",
                number_type="local",
            )
            raise AssertionError("expected 429 to propagate")
        except ProviderError as exc:
            assert (exc.details or {}).get("status") == 429

    async def _run_404():
        rows = await _search_or_empty(
            _Client(ProviderError("missing", details={"status": 404})),
            country_iso="US",
            number_type="local",
        )
        assert rows == []

    asyncio.run(_run_429())
    asyncio.run(_run_404())


def test_fetch_pricing_reraises_auth():
    from app.providers.errors import ProviderAuthError
    from app.providers.twilio.client import TwilioClient

    client = TwilioClient(
        ConnectionConfig(
            base_url="https://api.twilio.com/2010-04-01",
            auth_settings={"account_sid": "ACtest", "auth_token": "token"},
        )
    )

    async def _boom(*_args, **_kwargs):
        raise ProviderAuthError("Twilio auth failed HTTP 401", details={"status": 401})

    client._get = _boom  # type: ignore[method-assign]

    async def _run():
        try:
            await client.fetch_pricing("US")
            raise AssertionError("expected ProviderAuthError")
        except ProviderAuthError:
            return

    asyncio.run(_run())


def test_wipe_twilio_locked_busy_and_self_held(monkeypatch):
    from types import SimpleNamespace

    from app.modules.twilio import runner as twilio_runner
    from app.providers.errors import ProviderError

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(twilio_runner.lock_engine, "connect", lambda: _Conn())
    monkeypatch.setattr(twilio_runner, "try_advisory_lock_conn", lambda *_args, **_kwargs: False)
    try:
        twilio_runner.wipe_twilio_locked(SimpleNamespace())
        raise AssertionError("expected ProviderError")
    except ProviderError as exc:
        assert "уже выполняется" in str(exc)

    calls: list[object] = []

    def _lock(*_args, **_kwargs):
        calls.append("lock")
        return True

    def _reclaim(db, *, lock_free=None):
        calls.append(("reclaim", lock_free))
        return 1

    def _provider(_db):
        return SimpleNamespace(id="11111111-1111-1111-1111-111111111111")

    def _wipe(_db, *, provider_id):
        calls.append(("wipe", str(provider_id)))
        return {"numbers": 1}

    def _unlock(*_args, **_kwargs):
        calls.append("unlock")

    monkeypatch.setattr(twilio_runner, "try_advisory_lock_conn", _lock)
    monkeypatch.setattr(twilio_runner, "reclaim_stale_twilio_jobs", _reclaim)
    monkeypatch.setattr(twilio_runner, "get_twilio_provider", _provider)
    monkeypatch.setattr(twilio_runner, "wipe_twilio_data", _wipe)
    monkeypatch.setattr(twilio_runner, "advisory_unlock_conn", _unlock)
    assert twilio_runner.wipe_twilio_locked(SimpleNamespace()) == {"numbers": 1}
    assert calls[0] == "lock"
    assert calls[1] == ("reclaim", True)
    assert calls[2][0] == "wipe"
    assert calls[-1] == "unlock"


def test_numbers_sync_in_both_or_neither():
    from pydantic import ValidationError

    from app.schemas.twilio import TwilioNumbersSyncIn

    assert TwilioNumbersSyncIn().country_iso is None
    assert TwilioNumbersSyncIn(country_iso="us", number_type="local").country_iso == "US"
    try:
        TwilioNumbersSyncIn(country_iso="US")
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_runner_stages_are_sample_not_geo_grid():
    from app.modules.twilio.runner import STAGES

    assert [sid for sid, _label in STAGES] == ["countries", "pricing", "sample", "cutover"]
