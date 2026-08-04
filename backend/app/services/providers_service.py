from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.catalog import NumbersCatalogNormalized
from app.models.enums import ConnectionTestStatus, InventoryKind, ProviderCode
from app.models.providers import Provider, ProviderConnection
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderError
from app.providers.registry import get_provider
from app.schemas.providers import (
    ProviderCapability,
    ProviderHealthOut,
    ProviderOut,
    ProviderSettingsOut,
    ProviderSettingsUpdate,
    TestConnectionOut,
)

# Non-secret / display-safe auth fields (still docs-derived metadata)
_AUTH_PLAIN_KEYS = frozenset(
    {
        "email",
        "user_id",
        "token_expire",
        "refresh_token_expire",
        "numbering_login",
        "numbering_partition",
        "numbering_base_url",
    }
)
_AUTH_TOKEN_KEYS = frozenset(
    {"token", "access_token", "refresh_token", "token_expire", "refresh_token_expire"}
)
_AUTH_NUMBERING_SESSION_KEYS = frozenset({"numbering_session_id"})


def _mask_auth(auth: dict) -> dict:
    out = {}
    for k, v in (auth or {}).items():
        if v is None or v == "" or k in _AUTH_PLAIN_KEYS:
            out[k] = v
        else:
            s = str(v)
            out[k] = ("*" * max(0, len(s) - 4)) + s[-4:] if len(s) > 4 else "****"
    return out


def persist_auth_settings(conn: ProviderConnection, auth_settings: dict) -> None:
    conn.auth_settings = dict(auth_settings or {})
    flag_modified(conn, "auth_settings")


class ProvidersService:
    def __init__(self, db: Session):
        self.db = db

    def list_providers(self) -> list[ProviderOut]:
        rows = self.db.scalars(select(Provider).order_by(Provider.code)).all()
        result = []
        for p in rows:
            adapter = get_provider(p.code)
            caps_raw = adapter.capabilities()
            caps = {k: ProviderCapability(**v) for k, v in caps_raw.items()}
            conn = p.connection
            result.append(
                ProviderOut(
                    id=p.id,
                    code=p.code.value,
                    name=p.name,
                    is_enabled=p.is_enabled,
                    capabilities=caps,
                    last_tested_at=conn.last_tested_at if conn else None,
                    last_test_status=conn.last_test_status.value if conn else None,
                )
            )
        return result

    def get_settings(self, code: str) -> ProviderSettingsOut:
        p = self._provider(code)
        conn = p.connection
        if code == ProviderCode.runexis.value:
            notice = (
                "Runexis: DIDAPI email/password → Bearer (purchased); "
                "Numbering numbering_login/password → JSON-RPC connect (free catalog). "
                "See runexis-contract.md + runexis-numbering-api-contract.md."
            )
        elif code == ProviderCode.uis.value:
            notice = (
                "UIS Data API: access_token (API key from ЛК). "
                "IP whitelist required in UIS ЛК. See uis-contract.md. Read-only get.* only."
            )
        elif code == ProviderCode.aurora.value:
            notice = (
                "Aurora Telecom: public free CSV over HTTP (no auth). "
                "base_url is the full CSV URL. See aurora-contract.md. Free inventory only."
            )
        else:
            notice = (
                "Provider integration is based on uploaded documentation contracts "
                "under docs/providers/*-contract.md"
            )
        if not conn:
            return ProviderSettingsOut(
                provider_code=code,
                auth_settings_masked={},
                is_enabled=True,
                docs_notice=notice,
            )
        return ProviderSettingsOut(
            provider_code=code,
            base_url=conn.base_url,
            auth_settings_masked=_mask_auth(conn.auth_settings),
            extra_settings=conn.extra_settings or {},
            is_enabled=conn.is_enabled,
            last_tested_at=conn.last_tested_at,
            last_test_status=conn.last_test_status.value,
            last_test_message=conn.last_test_message,
            docs_notice=notice,
        )

    def upsert_settings(self, code: str, payload: ProviderSettingsUpdate) -> ProviderSettingsOut:
        p = self._provider(code)
        conn = p.connection
        if not conn:
            conn = ProviderConnection(provider_id=p.id, auth_settings={}, extra_settings={})
            self.db.add(conn)
        if payload.base_url is not None:
            conn.base_url = payload.base_url
        if payload.auth_settings is not None:
            incoming = {k: v for k, v in payload.auth_settings.items() if v not in (None, "")}
            merged = dict(conn.auth_settings or {})
            password_changed = (
                "password" in incoming and incoming.get("password") != merged.get("password")
            )
            numbering_password_changed = (
                "numbering_password" in incoming
                and incoming.get("numbering_password") != merged.get("numbering_password")
            )
            merged.update(incoming)
            if code == ProviderCode.runexis.value and password_changed:
                for key in _AUTH_TOKEN_KEYS:
                    merged.pop(key, None)
            if code == ProviderCode.runexis.value and numbering_password_changed:
                for key in _AUTH_NUMBERING_SESSION_KEYS:
                    merged.pop(key, None)
            persist_auth_settings(conn, merged)
        if payload.extra_settings is not None:
            conn.extra_settings = payload.extra_settings
        if payload.is_enabled is not None:
            conn.is_enabled = payload.is_enabled
            p.is_enabled = payload.is_enabled
        self.db.commit()
        return self.get_settings(code)

    async def test_connection(self, code: str) -> TestConnectionOut:
        p = self._provider(code)
        conn = p.connection
        if not conn:
            raise ProviderError("Connection settings missing")
        adapter = get_provider(p.code)
        cfg = ConnectionConfig(
            base_url=conn.base_url,
            auth_settings=dict(conn.auth_settings or {}),
            extra_settings=conn.extra_settings or {},
        )
        result = await adapter.test_connection(cfg)
        persist_auth_settings(conn, cfg.auth_settings)
        conn.last_tested_at = result.checked_at
        conn.last_test_status = (
            ConnectionTestStatus.ok if result.ok else ConnectionTestStatus.failed
        )
        conn.last_test_message = result.message
        self.db.commit()
        return TestConnectionOut(
            ok=result.ok,
            message=result.message,
            checked_at=result.checked_at,
            details=result.details,
        )

    def health(self, code: str | None = None) -> list[ProviderHealthOut]:
        q = select(Provider)
        if code:
            q = q.where(Provider.code == ProviderCode(code))
        rows = self.db.scalars(q).all()
        out = []
        for p in rows:
            adapter = get_provider(p.code)
            caps = {k: ProviderCapability(**v) for k, v in adapter.capabilities().items()}
            free_count = (
                self.db.scalar(
                    select(func.count())
                    .select_from(NumbersCatalogNormalized)
                    .where(
                        NumbersCatalogNormalized.provider_id == p.id,
                        NumbersCatalogNormalized.inventory_kind == InventoryKind.free,
                        NumbersCatalogNormalized.is_currently_present.is_(True),
                    )
                )
                or 0
            )
            purchased_count = (
                self.db.scalar(
                    select(func.count())
                    .select_from(NumbersCatalogNormalized)
                    .where(
                        NumbersCatalogNormalized.provider_id == p.id,
                        NumbersCatalogNormalized.inventory_kind == InventoryKind.purchased,
                        NumbersCatalogNormalized.is_currently_present.is_(True),
                    )
                )
                or 0
            )
            conn = p.connection
            limitations = []
            for name, cap in caps.items():
                if not cap.supported:
                    limitations.append(f"{name}: capability limited by documentation")
            out.append(
                ProviderHealthOut(
                    provider_code=p.code.value,
                    connection_status=conn.last_test_status.value if conn else "never_tested",
                    last_tested_at=conn.last_tested_at if conn else None,
                    free_count=free_count,
                    purchased_count=purchased_count,
                    capabilities=caps,
                    limitations=limitations,
                )
            )
        return out

    def _provider(self, code: str) -> Provider:
        p = self.db.scalar(select(Provider).where(Provider.code == ProviderCode(code)))
        if not p:
            raise ProviderError(f"Provider not found: {code}")
        return p
