from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SyncLogOut(BaseModel):
    id: UUID
    level: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class StageProgressOut(BaseModel):
    current: int | None = None
    total: int | None = None
    unit: str = ""


class SyncStageOut(BaseModel):
    id: str
    group: str
    label: str
    status: str
    detail: str = ""
    substage: str = ""
    progress: StageProgressOut = Field(default_factory=StageProgressOut)
    started_at: str | None = None
    finished_at: str | None = None


class SyncProgressOut(BaseModel):
    current_stage_id: str | None = None
    stages: list[SyncStageOut] = Field(default_factory=list)


class SyncRunOut(BaseModel):
    id: UUID
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: SyncProgressOut
    stats: dict[str, Any] = Field(default_factory=dict)
    error_summary: str | None = None
    triggered_by: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
