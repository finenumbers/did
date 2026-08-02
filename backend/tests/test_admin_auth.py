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
