from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.enums import ProviderCode
from app.providers.dto.common import ConnectionConfig, DiagnosticsResult, SyncResult


class AbstractProvider(ABC):
    """Documentation-driven provider orchestrator interface."""

    code: ProviderCode

    @abstractmethod
    async def test_connection(self, connection: ConnectionConfig) -> DiagnosticsResult:
        raise NotImplementedError

    @abstractmethod
    async def sync_regions(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        raise NotImplementedError

    @abstractmethod
    async def sync_cities(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        raise NotImplementedError

    @abstractmethod
    async def sync_free_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        raise NotImplementedError

    @abstractmethod
    async def sync_purchased_numbers(self, connection: ConnectionConfig, **kwargs: Any) -> SyncResult:
        raise NotImplementedError

    def capabilities(self) -> dict[str, Any]:
        """Capability summary for admin UI (override per provider)."""
        return {}
