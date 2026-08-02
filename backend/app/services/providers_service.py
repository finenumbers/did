from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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


def _mask_auth(auth: dict) -> dict:
    out = {}
    for k, v in (auth or {}).items():
        if v is None or v == "":
            out[k] = v
        else:
            s = str(v)
            out[k] = ("*" * max(0, len(s) - 4)) + s[-4:] if len(s) > 4 else "****"
    return out


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
        if not conn:
            return ProviderSettingsOut(provider_code=code, auth_settings_masked={}, is_enabled=True)
        return ProviderSettingsOut(
            provider_code=code,
            base_url=conn.base_url,
            auth_settings_masked=_mask_auth(conn.auth_settings),
            extra_settings=conn.extra_settings or {},
            is_enabled=conn.is_enabled,
            last_tested_at=conn.last_tested_at,
            last_test_status=conn.last_test_status.value,
            last_test_message=conn.last_test_message,
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
            merged = dict(conn.auth_settings or {})
            merged.update(payload.auth_settings)
            conn.auth_settings = merged
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
            auth_settings=conn.auth_settings or {},
            extra_settings=conn.extra_settings or {},
        )
        result = await adapter.test_connection(cfg)
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
