from __future__ import annotations

from pydantic import BaseModel, Field


class ExportJobCreate(BaseModel):
    sort_by: str | None = "abc_code"
    sort_dir: str = Field(default="asc", pattern="^(asc|desc)$")
    filters: str | None = None
    number_local_q: str | None = None


class ExportJobOut(BaseModel):
    id: str
    inventory_kind: str
    status: str
    phase: str | None = None
    rows_done: int = 0
    rows_total: int | None = None
    from_snapshot: bool = False
    error: str | None = None
    filename: str
    ticket: str | None = None
    created_at: str | None = None
    finished_at: str | None = None
