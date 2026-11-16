"""Settings return operator credentials in full and saves leave session keys alone."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.enums import ConnectionTestStatus
from app.providers.errors import ProviderError
from app.schemas.providers import ProviderSettingsUpdate
from app.services.providers_service import (
    ProvidersService,
    _mask_auth,
    merge_auth_settings,
    open_auth_settings,
)

PEM = "-----BEGIN PRIVATE KEY-----\nline\n-----END PRIVATE KEY-----"
PEM_NEW = "-----BEGIN PRIVATE KEY-----\nnew-line\n-----END PRIVATE KEY-----"


def test_open_auth_hides_runexis_session_and_keeps_passwords():
    auth = {
        "email": "a@b.c",
        "password": "p@ss word",
        "token": "bearer-token-value",
        "refresh_token": "refresh-token-value",
        "token_expire": "1",
        "refresh_token_expire": "2",
        "access_token": "legacy-bearer",
        "numbering_login": "num",
        "numbering_password": "num-secret",
        "numbering_session_id": "sess",
        "numbering_partition": "part",
        "numbering_base_url": "https://did-api.runexis.ru/",
    }
    opened = open_auth_settings("runexis", auth)
    assert opened["password"] == "p@ss word"
    assert opened["numbering_password"] == "num-secret"
    assert opened["email"] == "a@b.c"
    for hidden in (
        "token",
        "refresh_token",
        "token_expire",
        "refresh_token_expire",
        "access_token",
        "numbering_session_id",
        "numbering_partition",
    ):
        assert hidden not in opened


def test_novofon_access_token_stays_visible_and_runtime_token_does_not():
    opened = open_auth_settings(
        "novofon",
        {"access_token": "cabinet-key", "api_secret": "secret-value", "token": "nope"},
    )
    assert opened["access_token"] == "cabinet-key"
    assert opened["api_secret"] == "secret-value"
    assert "token" not in opened


def test_mask_still_hides_password_and_shows_email():
    masked = _mask_auth({"password": "p@ss word", "email": "a@b.c"})
    assert masked["email"] == "a@b.c"
    assert masked["password"] != "p@ss word"
    assert masked["password"].endswith("word")
    assert set(masked["password"][:-4]) == {"*"}


def test_omitted_password_keeps_token():
    stored = {"password": "p@ss word", "token": "bearer", "refresh_token": "r", "email": "old"}
    merged = merge_auth_settings("runexis", stored, {"email": "a@b.c"})
    assert merged["password"] == "p@ss word"
    assert merged["token"] == "bearer"
    assert merged["refresh_token"] == "r"
    assert merged["email"] == "a@b.c"
    assert stored["token"] == "bearer"


def test_new_password_drops_runexis_tokens():
    stored = {
        "password": "p@ss word",
        "token": "bearer",
        "refresh_token": "r",
        "access_token": "legacy",
        "token_expire": "1",
        "refresh_token_expire": "2",
    }
    merged = merge_auth_settings("runexis", stored, {"password": "next-secret"})
    assert merged["password"] == "next-secret"
    for key in ("token", "refresh_token", "access_token", "token_expire", "refresh_token_expire"):
        assert key not in merged


def test_blank_password_removes_it_and_drops_tokens():
    stored = {"password": "p@ss word", "token": "bearer", "refresh_token": "r"}
    merged = merge_auth_settings("runexis", stored, {"password": "   "})
    assert "password" not in merged
    assert "token" not in merged
    assert "refresh_token" not in merged


def test_blank_password_when_unset_does_not_drop_tokens():
    stored = {"token": "bearer", "email": "a@b.c"}
    merged = merge_auth_settings("runexis", stored, {"password": ""})
    assert merged["token"] == "bearer"
    assert "password" not in merged


def test_internal_space_in_password_is_kept_and_same_value_keeps_token():
    stored = {"password": "a b", "token": "bearer"}
    merged = merge_auth_settings("runexis", stored, {"password": "a b"})
    assert merged["password"] == "a b"
    assert merged["token"] == "bearer"


def test_omitted_numbering_password_keeps_session_and_partition():
    stored = {
        "numbering_password": "num-secret",
        "numbering_session_id": "sess",
        "numbering_partition": "part",
    }
    merged = merge_auth_settings("runexis", stored, {"email": "a@b.c"})
    assert merged["numbering_session_id"] == "sess"
    assert merged["numbering_partition"] == "part"
    assert merged["numbering_password"] == "num-secret"


def test_cleared_numbering_password_drops_session_and_keeps_partition():
    stored = {
        "numbering_password": "num-secret",
        "numbering_session_id": "sess",
        "numbering_partition": "part",
    }
    merged = merge_auth_settings("runexis", stored, {"numbering_password": ""})
    assert "numbering_password" not in merged
    assert "numbering_session_id" not in merged
    assert merged["numbering_partition"] == "part"


def test_mcn_key_change_keeps_header_mode():
    stored = {"api_key": "old-key", "auth_header_mode": "bearer"}
    merged = merge_auth_settings("mcn", stored, {"api_key": "new-key"})
    assert merged == {"api_key": "new-key", "auth_header_mode": "bearer"}


def test_blank_api_key_is_removed():
    merged = merge_auth_settings("sipout", {"key": "sip-key-value"}, {"key": " \n "})
    assert merged == {}


def test_novofon_blank_user_id_is_removed_and_omitted_user_id_stays():
    stored = {"user_id": "15", "access_token": "cabinet-key"}
    cleared = merge_auth_settings("novofon", stored, {"user_id": ""})
    assert "user_id" not in cleared
    assert cleared["access_token"] == "cabinet-key"
    kept = merge_auth_settings("novofon", stored, {"api_key": "optional"})
    assert kept["user_id"] == "15"
    assert kept["access_token"] == "cabinet-key"
    assert kept["api_key"] == "optional"


def test_vox_json_replaces_private_key_already_stored():
    stored = {"account_id": 1, "key_id": "old", "private_key": PEM}
    raw = json.dumps({"account_id": 9, "key_id": "new", "private_key": PEM_NEW})
    merged = merge_auth_settings("voximplant", stored, {"credentials_json": raw})
    assert merged["account_id"] == 9
    assert merged["key_id"] == "new"
    assert merged["private_key"] == PEM_NEW
    assert "credentials_json" not in merged
    assert stored["private_key"] == PEM


def test_vox_blank_json_clears_credentials_only():
    stored = {
        "account_id": 1,
        "key_id": "old",
        "private_key": PEM,
        "auth_header_mode": "x",
    }
    merged = merge_auth_settings("voximplant", stored, {"credentials_json": "  "})
    assert "account_id" not in merged
    assert "key_id" not in merged
    assert "private_key" not in merged
    assert merged["auth_header_mode"] == "x"


def test_vox_invalid_json_raises_and_leaves_stored_dict():
    stored = {"account_id": 1, "key_id": "k", "private_key": PEM}
    with pytest.raises(ProviderError, match="not valid JSON"):
        merge_auth_settings("voximplant", stored, {"credentials_json": "{"})
    assert stored["private_key"] == PEM


def _conn(**kwargs):
    data = {
        "base_url": "https://example.test",
        "auth_settings": {},
        "extra_settings": {},
        "is_enabled": True,
        "last_tested_at": None,
        "last_test_status": ConnectionTestStatus.never_tested,
        "last_test_message": None,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def _service(conn):
    provider = SimpleNamespace(connection=conn, is_enabled=True, id="provider-1")
    db = MagicMock()
    db.scalar.return_value = provider
    return ProvidersService(db), db


def test_get_settings_returns_full_secret_and_keeps_the_mask():
    conn = _conn(
        base_url="https://api.exolve.ru",
        auth_settings={"api_key": "exolve-secret-key", "auth_header_mode": "bearer"},
    )
    svc, _db = _service(conn)
    out = svc.get_settings("exolve")
    assert out.auth_settings["api_key"] == "exolve-secret-key"
    assert "auth_header_mode" not in out.auth_settings
    assert out.auth_settings_masked["api_key"] != "exolve-secret-key"
    assert "*" in out.auth_settings_masked["api_key"]

    vox = _conn(auth_settings={"account_id": 7, "key_id": "kid", "private_key": PEM})
    vox_out = _service(vox)[0].get_settings("voximplant")
    assert vox_out.auth_settings["private_key"] == PEM
    assert "*" in vox_out.auth_settings_masked["private_key"]


def test_upsert_invalid_vox_json_does_not_commit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.providers_service.flag_modified", lambda *_a, **_k: None)
    conn = _conn(auth_settings={"account_id": 1, "key_id": "k", "private_key": PEM})
    svc, db = _service(conn)
    with pytest.raises(ProviderError, match="not valid JSON"):
        svc.upsert_settings(
            "voximplant",
            ProviderSettingsUpdate(auth_settings={"credentials_json": "{"}),
        )
    db.commit.assert_not_called()
    assert conn.auth_settings["private_key"] == PEM


def test_upsert_blank_reg_url_removes_only_that_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.providers_service.flag_modified", lambda *_a, **_k: None)
    conn = _conn(
        auth_settings={"key": "pstn-key"},
        extra_settings={"reg_base_url": "https://reg.example", "keep": 1},
    )
    svc, db = _service(conn)
    out = svc.upsert_settings(
        "finenumbers",
        ProviderSettingsUpdate(extra_settings={"reg_base_url": "  "}),
    )
    assert conn.extra_settings == {"keep": 1}
    assert conn.auth_settings["key"] == "pstn-key"
    assert out.auth_settings["key"] == "pstn-key"
    db.commit.assert_called_once()
