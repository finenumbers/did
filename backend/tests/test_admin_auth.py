from app.core.security import (
    auth_enabled,
    issue_session_token,
    verify_password,
    verify_session_token,
)


def test_password_and_token(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert auth_enabled() is True
    assert verify_password("admin", "secret") is True
    assert verify_password("admin", "wrong") is False
    token = issue_session_token("admin")
    assert verify_session_token(token) == "admin"
    get_settings.cache_clear()


def test_did_require_auth_needs_login_creds(monkeypatch):
    """Token alone must not satisfy DID_REQUIRE_AUTH."""
    monkeypatch.setenv("DID_REQUIRE_AUTH", "1")
    monkeypatch.setenv("ADMIN_API_TOKEN", "machine-only")
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    from app.core.config import get_settings
    from app.core.security import auth_enabled

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.did_require_auth is True
    assert auth_enabled() is False
    get_settings.cache_clear()


def test_middleware_rejects_query_access_token(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-secret")
    from app.core.config import get_settings
    from app.core.security import issue_session_token, is_authorized_bearer

    get_settings.cache_clear()
    token = issue_session_token("admin")
    assert is_authorized_bearer(f"Bearer {token}") is True
    # Query-string tokens are no longer accepted by middleware; bare token is not a Bearer header.
    assert is_authorized_bearer(token) is False
    get_settings.cache_clear()
