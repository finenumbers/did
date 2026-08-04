"""Admin session tokens (HMAC) and password check from env credentials."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings

SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def auth_enabled() -> bool:
    s = get_settings()
    return bool((s.admin_username or "").strip() and (s.admin_password or "").strip())


def _session_secret() -> str:
    s = get_settings()
    secret = (s.admin_session_secret or "").strip()
    if secret:
        return secret
    # Derive stable secret from password so tokens survive restarts without extra env
    material = f"{s.admin_username}:{s.admin_password}:did-session"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def verify_password(username: str, password: str) -> bool:
    s = get_settings()
    expected_user = (s.admin_username or "").strip()
    expected_pass = (s.admin_password or "").strip()
    if not expected_user or not expected_pass:
        return False
    user_ok = hmac.compare_digest(username.strip(), expected_user)
    pass_ok = hmac.compare_digest(password, expected_pass)
    return user_ok and pass_ok


def issue_session_token(username: str) -> str:
    payload: dict[str, Any] = {
        "u": username.strip(),
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    sig = hmac.new(
        _session_secret().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    raw = f"{body}.{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def verify_session_token(token: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        text = raw.decode("utf-8")
        body, sig = text.rsplit(".", 1)
        expected = hmac.new(
            _session_secret().encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(body)
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        user = str(payload.get("u") or "").strip()
        if not user:
            return None
        s = get_settings()
        if user != (s.admin_username or "").strip():
            return None
        return user
    except Exception:
        return None


def is_authorized_bearer(authorization: str | None) -> bool:
    """Accept session token or legacy ADMIN_API_TOKEN."""
    if not authorization or not authorization.startswith("Bearer "):
        return False
    token = authorization[7:].strip()
    if not token:
        return False
    s = get_settings()
    legacy = (s.admin_api_token or "").strip()
    if legacy and hmac.compare_digest(token, legacy):
        return True
    if auth_enabled() and verify_session_token(token):
        return True
    return False



def api_protection_enabled() -> bool:
    s = get_settings()
    return auth_enabled() or bool((s.admin_api_token or "").strip())
