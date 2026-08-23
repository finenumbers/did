"""Twilio provider — connection test only. Coverage sync lives in app.modules.twilio."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.enums import ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncLimitation, SyncResult
from app.providers.errors import ProviderError
from app.providers.twilio import contract
from app.providers.twilio.client import TwilioClient


class TwilioProvider(AbstractProvider):
    code = ProviderCode.twilio

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": False,
                "source": "out_of_scope",
                "action": None,
                "reason_code": "twilio_isolated_catalog",
            },
            "purchased_numbers": {
                "supported": False,
                "source": "out_of_scope",
                "action": None,
            },
            "dictionaries": {
                "supported": True,
                "source": "documentation_verified",
                "actions": ["GET AvailablePhoneNumbers.json"],
                "doc_refs": [contract.DOC_REFS["available"]],
            },
            "twilio_coverage": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET AvailablePhoneNumbers + Pricing PhoneNumbers/Countries",
                "doc_refs": [contract.DOC_REFS["available"], contract.DOC_REFS["pricing"]],
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET AvailablePhoneNumbers.json",
                "doc_refs": [contract.DOC_REFS["available"]],
            },
        }

    def _unsupported(self, capability: str) -> SyncResult:
        return SyncResult(
            limitations=[
                SyncLimitation(
                    provider="twilio",
                    capability=capability,
                    message="Twilio is not part of the RU free-numbers catalog",
                    doc_refs=[contract.DOC_REFS["available"]],
                )
            ]
        )

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        try:
            client = TwilioClient(connection)
        except ProviderError as exc:
            return DiagnosticsResult(
                ok=False,
                message=str(exc),
                checked_at=datetime.now(timezone.utc),
                details=exc.details,
            )
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
            message=f"Twilio GET AvailablePhoneNumbers OK ({len(items)} countries)",
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
