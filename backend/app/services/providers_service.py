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
        "account_id",
        "key_id",
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
                "Configure file URLs in extra_settings.csv_files "
                "(optional has_status_column for MSK-style 6-col). See aurora-contract.md."
            )
        elif code == ProviderCode.exolve.value:
            notice = (
                "Exolve: Bearer api_key from Settings. Read-only GetList + GetFree "
                "(type×all regions). See exolve-contract.md. Purchased/Lock/Buy out of scope."
            )
        elif code == ProviderCode.voximplant.value:
            notice = (
                "Voximplant: paste Service Account credentials.json (account_id, key_id, "
                "private_key). JWT RS256 → Management API. Read-only RU Categories/Regions/"
                "GetNewPhoneNumbers (all free). See voximplant-contract.md. Attach/purchased OOS."
            )
        elif code == ProviderCode.mcn.value:
            notice = (
                "MCN Telecom: api_key = Integrations token from LK. Read-only Витрина "
                "(shop.mcn.ru) countries/regions/cities/numbers for RU=643. "
                "See mcn-contract.md. Checkout/NNP/purchased out of scope."
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
            if code == ProviderCode.voximplant.value:
                from app.providers.voximplant.auth_jwt import parse_credentials

                try:
                    creds = parse_credentials(merged)
                except ProviderError as exc:
                    raise ProviderError(str(exc)) from exc
                merged = {
                    "account_id": creds["account_id"],
                    "key_id": creds["key_id"],
                    "private_key": creds["private_key"],
                }
            persist_auth_settings(conn, merged)
        if payload.extra_settings is not None:
            if code == ProviderCode.aurora.value:
                from app.providers.aurora import contract as aurora_contract

                entries = aurora_contract.normalize_csv_files(
                    payload.extra_settings.get("csv_files"),
                    require_non_empty=True,
                )
                conn.extra_settings = {
                    "csv_files": [e.to_dict() for e in entries],
                }
                flag_modified(conn, "extra_settings")
                # Aurora sync reads only csv_files; clear misleading base_url.
                if payload.base_url is None:
                    conn.base_url = None
            else:
                merged_extra = dict(conn.extra_settings or {})
                for key, value in payload.extra_settings.items():
                    if value in (None, ""):
                        continue
                    merged_extra[key] = value
                conn.extra_settings = merged_extra
                flag_modified(conn, "extra_settings")
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
