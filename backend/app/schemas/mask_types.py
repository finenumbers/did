from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MaskTypeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    digit_capacity: str
    category: str
    abc: str
    mask: str
    type_label: str | None = None
    premium: str | None = None
    purchase: str | None = None


class MaskTypesLoadResult(BaseModel):
    ok: bool = True
    count: int
    updated: int = 0
    inserted: int = 0
    message: str
