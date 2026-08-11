"""Build Voximplant Management API JWTs from service-account credentials."""

from __future__ import annotations

import json
import time
from typing import Any

from jwt.api_jws import PyJWS

from app.providers.errors import ProviderAuthError
from app.providers.voximplant import contract


def normalize_private_key(raw: str) -> str:
    key = (raw or "").strip()
    if "\\n" in key and "-----BEGIN" in key:
        key = key.replace("\\n", "\n")
    return key


def parse_credentials(auth_settings: dict[str, Any] | None) -> dict[str, Any]:
    """Return {account_id:int, key_id:str, private_key:str} from auth_settings."""
    auth = dict(auth_settings or {})
    if auth.get(contract.AUTH_CREDENTIALS_JSON) and not (
        auth.get(contract.AUTH_ACCOUNT_ID)
        and auth.get(contract.AUTH_KEY_ID)
        and auth.get(contract.AUTH_PRIVATE_KEY)
    ):
        raw = auth.get(contract.AUTH_CREDENTIALS_JSON)
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProviderAuthError(
                    "Voximplant credentials_json is not valid JSON"
                ) from exc
            if not isinstance(parsed, dict):
                raise ProviderAuthError("Voximplant credentials_json must be an object")
            auth.update(parsed)
        elif isinstance(raw, dict):
            auth.update(raw)

    account_id = auth.get(contract.AUTH_ACCOUNT_ID)
    key_id = auth.get(contract.AUTH_KEY_ID)
    private_key = auth.get(contract.AUTH_PRIVATE_KEY)
    if account_id is None or key_id is None or not private_key:
        raise ProviderAuthError(
            "Voximplant requires account_id, key_id, private_key "
            "(paste Service Account credentials.json in Settings)"
        )
    try:
        account_id_int = int(account_id)
    except (TypeError, ValueError) as exc:
        raise ProviderAuthError(
            f"Voximplant account_id must be an integer, got {account_id!r}"
        ) from exc
    key_id_s = str(key_id).strip()
    if not key_id_s:
        raise ProviderAuthError("Voximplant key_id is empty")
    pem = normalize_private_key(str(private_key))
    if "BEGIN" not in pem:
        raise ProviderAuthError("Voximplant private_key must be a PEM private key")
    return {
        contract.AUTH_ACCOUNT_ID: account_id_int,
        contract.AUTH_KEY_ID: key_id_s,
        contract.AUTH_PRIVATE_KEY: pem,
    }


def build_bearer_token(
    creds: dict[str, Any],
    *,
    now: int | None = None,
    ttl_seconds: int = contract.JWT_TTL_SECONDS,
) -> tuple[str, int]:
    """Return (jwt, exp_unix).

    Voximplant requires numeric ``iss`` (account_id). PyJWT's high-level
    ``encode`` rejects non-string iss, so we sign via PyJWS.
    """
    iat = int(now if now is not None else time.time())
    exp = iat + min(int(ttl_seconds), contract.JWT_TTL_SECONDS)
    payload = json.dumps(
        {
            "iat": iat,
            "iss": int(creds[contract.AUTH_ACCOUNT_ID]),
            "exp": exp,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    token = PyJWS().encode(
        payload,
        creds[contract.AUTH_PRIVATE_KEY],
        algorithm="RS256",
        headers={
            "typ": "JWT",
            "kid": creds[contract.AUTH_KEY_ID],
        },
    )
    if isinstance(token, bytes):
        token = token.decode("ascii")
    return token, exp


class JwtTokenCache:
    def __init__(self, auth_settings: dict[str, Any] | None):
        self._creds = parse_credentials(auth_settings)
        self._token: str | None = None
        self._exp: int = 0

    @property
    def credentials(self) -> dict[str, Any]:
        return self._creds

    def get_token(self) -> str:
        now = int(time.time())
        if (
            self._token
            and now < self._exp - contract.JWT_REFRESH_SKEW_SECONDS
        ):
            return self._token
        self._token, self._exp = build_bearer_token(self._creds, now=now)
        return self._token
