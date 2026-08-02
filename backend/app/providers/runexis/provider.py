"""Runexis orchestrator. Docs: Runexis.html + runexis-contract.md."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.enums import ProviderCode
from app.providers.base import AbstractProvider
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncLimitation, SyncResult
from app.providers.errors import ProviderCapabilityLimitedError
from app.providers.runexis import contract, parser
from app.providers.runexis.client import RunexisClient


class RunexisProvider(AbstractProvider):
    code = ProviderCode.runexis

    def capabilities(self) -> dict[str, Any]:
        return {
            "free_numbers": {
                "supported": False,
                "source": "unresolved",
                "reason_code": "PROVIDER_CAPABILITY_LIMITED",
                "doc_refs": contract.DOC_REFS_LIMITATIONS,
            },
            "purchased_numbers": {
                "supported": False,
                "source": "unresolved",
                "reason_code": "PROVIDER_CAPABILITY_LIMITED",
                "doc_refs": contract.DOC_REFS_LIMITATIONS,
            },
            "dictionaries": {
                "supported": True,
                "source": "documentation_verified",
                "actions": ["GET api/v1/regions", "GET api/v1/regions/cities"],
            },
            "test_connection": {
                "supported": True,
                "source": "documentation_verified",
                "action": "GET api/v1/me",
            },
        }

    def _client(self, connection: ConnectionConfig) -> RunexisClient:
        return RunexisClient(connection)

    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        # VERIFIED: GET api/v1/me
        client = self._client(connection)
        raw = await client.get_me()
        try:
            parser.parse_me(raw)
            ok = 200 <= raw.status_code < 300
            return DiagnosticsResult(
                ok=ok,
                message="Runexis GET api/v1/me succeeded" if ok else f"status={raw.status_code}",
                checked_at=datetime.now(timezone.utc),
                details={"endpoint": contract.GET_ME},
                raw=raw,
            )
        except Exception as exc:
            return DiagnosticsResult(
                ok=False,
                message=str(exc),
                checked_at=datetime.now(timezone.utc),
                details={"endpoint": contract.GET_ME},
                raw=raw,
            )

    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # VERIFIED: GET api/v1/regions
        client = self._client(connection)
        raw = await client.get_regions()
        regions = parser.parse_regions(raw)
        return SyncResult(
            fetched=len(regions),
            parsed=len(regions),
            items={"regions": regions, "cities": []},
            raw_envelopes=[raw],
        )

    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # VERIFIED: GET api/v1/regions/cities
        client = self._client(connection)
        raw = await client.get_cities()
        cities = parser.parse_cities(raw)
        return SyncResult(
            fetched=len(cities),
            parsed=len(cities),
            items={"regions": [], "cities": cities},
            raw_envelopes=[raw],
        )

    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        # No free inventory endpoint in uploaded docs — capability limited
        limitation = SyncLimitation(
            provider=self.code.value,
            capability="free_numbers",
            message=(
                "Runexis free-number sync is not available: no free inventory endpoint "
                "in uploaded documentation."
            ),
            doc_refs=contract.DOC_REFS_LIMITATIONS,
        )
        if kwargs.get("raise_on_limitation"):
            raise ProviderCapabilityLimitedError(
                limitation.message,
                provider=self.code.value,
                capability="free_numbers",
                doc_refs=limitation.doc_refs,
            )
        return SyncResult(limitations=[limitation], warnings=[limitation.message])

    async def sync_purchased_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        limitation = SyncLimitation(
            provider=self.code.value,
            capability="purchased_numbers",
            message=(
                "Runexis purchased-number sync is not available: no purchased inventory "
                "endpoint in uploaded documentation."
            ),
            doc_refs=contract.DOC_REFS_LIMITATIONS,
        )
        if kwargs.get("raise_on_limitation"):
            raise ProviderCapabilityLimitedError(
                limitation.message,
                provider=self.code.value,
                capability="purchased_numbers",
                doc_refs=limitation.doc_refs,
            )
        return SyncResult(limitations=[limitation], warnings=[limitation.message])
