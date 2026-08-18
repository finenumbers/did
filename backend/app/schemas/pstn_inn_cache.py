from typing import Any

from pydantic import BaseModel, Field


class PstnInnOperatorIn(BaseModel):
    name: str
    inn: str
    enabled: bool = True


class PstnInnOperatorUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None


class PstnInnOperatorOut(BaseModel):
    id: str
    name: str
    inn: str
    enabled: bool
    required: bool
    ranges_count: int
    numbers_count: int = 0
    last_synced_at: str | None = None
    last_error: str | None = None


class PstnInnCacheStatusOut(BaseModel):
    min_cache_ready: bool
    missing_required: list[str] = Field(default_factory=list)
    gar_territory_missing: bool = False
    refresh: dict[str, Any] = Field(default_factory=dict)
    operators: list[PstnInnOperatorOut] = Field(default_factory=list)


class SyncScheduleOut(BaseModel):
    enabled: bool
    timezone: str = "Europe/Moscow"
    hour: int = 0
    minute: int = 0


class SyncScheduleUpdate(BaseModel):
    enabled: bool
