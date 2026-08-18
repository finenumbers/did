"""Voximplant provider unit tests (no live API)."""

from __future__ import annotations

import asyncio

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderError
from app.providers.voximplant import contract, mapper, parser
from app.providers.voximplant.auth_jwt import build_bearer_token, parse_credentials
from app.providers.voximplant.client import VoximplantClient
from app.providers.voximplant.provider import VoximplantProvider
from app.models.enums import InventoryKind


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


PEM = _rsa_pem()


def _conn() -> ConnectionConfig:
    return ConnectionConfig(
        base_url="https://api.voximplant.com",
        auth_settings={
            "account_id": 12345,
            "key_id": "kid-1",
            "private_key": PEM,
        },
    )


def test_parse_credentials_from_json_string():
    import json

    blob = json.dumps(
        {"account_id": 99, "key_id": "abc", "private_key": PEM.replace("\n", "\\n")}
    )
    creds = parse_credentials({"credentials_json": blob})
    assert creds["account_id"] == 99
    assert creds["key_id"] == "abc"
    assert "BEGIN" in creds["private_key"]


def test_build_jwt_has_kid_and_iss():
    creds = parse_credentials(
        {"account_id": 42, "key_id": "k1", "private_key": PEM}
    )
    token, exp = build_bearer_token(creds, now=1_700_000_000)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == "k1"
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["iss"] == 42
    assert exp == 1_700_000_000 + 3600


def test_extract_ru_categories_filters():
    body = {
        "result": [
            {
                "country_code": "RU",
                "can_list_phone_numbers": True,
                "phone_categories": [
                    {"phone_category_name": "GEOGRAPHIC"},
                    {"phone_category_name": "MOBILE"},
                ],
            },
            {
                "country_code": "US",
                "can_list_phone_numbers": True,
                "phone_categories": [{"phone_category_name": "GEOGRAPHIC"}],
            },
        ]
    }
    cats = parser.extract_ru_categories(body)
    assert {c["phone_category_name"] for c in cats} == {"GEOGRAPHIC", "MOBILE"}


def test_api_error_envelope_raises():
    try:
        parser.raise_for_api_error({"error": {"code": 241, "msg": "bad region"}})
        assert False, "expected ProviderError"
    except ProviderError as exc:
        assert "241" in exc.code or "bad region" in str(exc)


def test_extract_new_phones_page_totals():
    body = {
        "result": [
            {"phone_number": "74951234567", "phone_price": 1, "phone_installation_price": 2}
        ],
        "total_count": 40,
        "count": 1,
    }
    items, total, returned = parser.extract_new_phones_page(body)
    assert len(items) == 1
    assert total == 40
    assert returned == 1


def test_map_number_prices_and_msisdn():
    parsed = parser.parse_number_item(
        {
            "phone_number": "74951234567",
            "phone_price": 0.45,
            "phone_installation_price": 10.2,
            "phone_category_name": "GEOGRAPHIC",
            "phone_region_name": "Moscow",
            "phone_id": 10,
            "phone_tax_reserve": 1,
        },
        category="GEOGRAPHIC",
        region_id=1,
    )
    num = mapper.map_number(parsed, inventory_kind=InventoryKind.free)
    assert num is not None
    assert num.msisdn == "74951234567"
    assert num.provider_number_key == "74951234567"
    assert float(num.period_price) == 0.45
    assert float(num.buy_price) == 10.2
    assert num.normalized_payload.get("phone_id") == 10


def test_iter_free_slice_shortfall_is_warning():
    client = VoximplantClient(_conn())

    async def fake_page(*, category, region_id, offset, count=None):
        if offset == 0:
            return (
                [{"phone_number": "74950000001"}],
                5,
                1,
                RawHttpResult(200, "{}", {}, {}, 1, "u"),
            )
        return ([], 5, 0, RawHttpResult(200, "{}", {}, {}, 1, "u"))

    client.get_new_phones_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, _envs, meta = await client.iter_free_slice(
            category="GEOGRAPHIC", region_id=1
        )
        assert len(items) == 1
        assert meta.get("slice_incomplete") is True
        assert meta["total_count"] == 5

    asyncio.run(run())


def test_iter_free_slice_uses_len_page_not_api_count():
    client = VoximplantClient(_conn(), page_limit=2)
    all_nums = [{"phone_number": f"7495000000{i}"} for i in range(1, 4)]

    async def fake_page(*, category, region_id, offset, count=None):
        page = all_nums[offset : offset + 1]
        return (
            page,
            3,
            2,
            RawHttpResult(200, "{}", {}, {}, 1, "u"),
        )

    client.get_new_phones_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, _envs, meta = await client.iter_free_slice(
            category="GEOGRAPHIC", region_id=1
        )
        phones = {str(it["phone_number"]) for it in items}
        assert phones == {"74950000001", "74950000002", "74950000003"}
        assert meta.get("slice_incomplete") is None

    asyncio.run(run())


def test_iter_free_slice_follows_shrinking_total_count():
    client = VoximplantClient(_conn(), page_limit=2)

    async def fake_page(*, category, region_id, offset, count=None):
        if offset == 0:
            return (
                [{"phone_number": "74950000001"}, {"phone_number": "74950000002"}],
                5,
                2,
                RawHttpResult(200, "{}", {}, {}, 1, "u"),
            )
        return ([], 2, 0, RawHttpResult(200, "{}", {}, {}, 1, "u"))

    client.get_new_phones_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, _envs, meta = await client.iter_free_slice(
            category="GEOGRAPHIC", region_id=1
        )
        assert len(items) == 2
        assert meta["total_count"] == 2
        assert meta.get("slice_incomplete") is None

    asyncio.run(run())


def test_iter_free_slice_full_pages():
    client = VoximplantClient(_conn(), page_limit=2)

    async def fake_page(*, category, region_id, offset, count=None):
        all_nums = [
            {"phone_number": f"7495000000{i}"} for i in range(1, 5)
        ]
        page = all_nums[offset : offset + 2]
        return (
            page,
            4,
            len(page),
            RawHttpResult(200, "{}", {}, {}, 1, "u"),
        )

    client.get_new_phones_page = fake_page  # type: ignore[method-assign]

    async def run():
        items, _envs, meta = await client.iter_free_slice(
            category="GEOGRAPHIC", region_id=1
        )
        assert len(items) == 4
        assert meta["total_count"] == 4

    asyncio.run(run())


def test_provider_capabilities():
    caps = VoximplantProvider().capabilities()
    assert caps["free_numbers"]["supported"] is True
    assert caps["purchased_numbers"]["supported"] is False
    assert caps["dictionaries"]["supported"] is True


def test_free_incomplete_is_warning_not_abort():
    """Global shortfall is a warning; fetched numbers are still returned."""
    from unittest.mock import AsyncMock, MagicMock

    provider = VoximplantProvider()
    conn = _conn()
    raw = RawHttpResult(200, "{}", {}, {}, 1, "u")

    client = MagicMock()
    client.get_account_info = AsyncMock(return_value=({"currency": "RUR"}, raw))
    client.get_ru_categories = AsyncMock(
        return_value=([{"phone_category_name": "GEOGRAPHIC"}], raw)
    )
    client.get_regions = AsyncMock(
        return_value=([{"phone_region_id": 1, "phone_count": 5}], raw)
    )

    async def fake_iter(
        *,
        category,
        region_id,
        region_name=None,
        on_progress=None,
        expected_phone_count=None,
    ):
        items = [
            {
                "phone_number": "74950000001",
                "phone_price": 1,
                "phone_installation_price": 0,
                "_vox_category": category,
                "_vox_region_id": region_id,
            },
            {
                "phone_number": "74950000002",
                "phone_price": 1,
                "phone_installation_price": 0,
                "_vox_category": category,
                "_vox_region_id": region_id,
            },
        ]
        return items, [], {"total_count": 5, "fetched": 2}

    client.iter_free_slice = fake_iter
    provider._client = lambda connection, **kwargs: client  # type: ignore[method-assign]

    async def run():
        result = await provider.sync_free_numbers(conn)
        assert len(result.items) == 2
        assert any("unique_keys=2" in w for w in result.warnings)
        assert result.extra_stats["integrity"]["incomplete"] is True

    asyncio.run(run())
