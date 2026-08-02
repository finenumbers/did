from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SyncStartRequest(BaseModel):
    mode: Literal["full", "free_only", "purchased_only", "dictionaries_only"] = "full"
    dry_run: bool = False
    include_dictionaries: bool = False


class SyncJobOut(BaseModel):
    id: UUID
    provider_code: str
    job_type: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    stats: dict[str, Any] = Field(default_factory=dict)
    error_summary: str | None = None
    triggered_by: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncLogOut(BaseModel):
    id: UUID
    level: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}
