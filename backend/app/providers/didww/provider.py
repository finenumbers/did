"""DIDWW provider — connection test only. Coverage sync lives in app.modules.didww (isolated)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.enums import ProviderCode
from app.providers.base import AbstractProvider
from app.providers.didww import contract
from app.providers.didww.client import DidwwClient
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncLimitation, SyncResult
from app.providers.errors import ProviderError


class DidwwProvider(AbstractProvider):
    code = ProviderCode.didww

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": False,
                "source": "out_of_scope",
                "action": None,
                "reason_code": "didww_isolated_catalog",
            },
            "purchased_numbers": {
                "supported": False,
                "source": "out_of_scope",
                "action": None,
            },
            "dictionaries": {
                "supported": True,
                "source": "documentation_verified",
                "actions": [
                    "GET /v3/countries",
                    "GET /v3/regions",
                    "GET /v3/cities",
                    "GET /v3/did_group_types",
                ],
                "doc_refs": [contract.DOC_REFS["getting_started"]],
            },
            "didww_coverage": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET /v3/did_groups?include=country,region,city,did_group_type,stock_keeping_units",
                "doc_refs": [contract.DOC_REFS["did_groups"]],
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET /v3/countries",
            },
        }

    def _unsupported(self, capability: str) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider="didww",
                    capability=capability,
                    message="DIDWW is not part of the RU free-numbers catalog",
                    doc_refs=[contract.DOC_REFS["did_groups"]],
                )
            ]
        )

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        client = DidwwClient(connection)
        try:
            items = await client.list_countries()
        except ProviderError as exc:
            return DiagnosticsResult(
                ok=False,
                message=str(exc),
                checked_at=datetime.now(timezone.utc),
                details=exc.details,
            )
        finally:
            await client.aclose()
        return DiagnosticsResult(
            ok=True,
            message=f"DIDWW GET /countries OK ({len(items)} countries)",
            checked_at=datetime.now(timezone.utc),
            details={"countries": len(items)},
        )

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return self._unsupported("sync_regions")

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return self._unsupported("sync_cities")

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return self._unsupported("sync_free_numbers")

    async def sync_purchased_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        return self._unsupported("sync_purchased_numbers")
