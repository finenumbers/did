from math import ceil
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)
    sort_by: str | None = None
    sort_dir: Literal["asc", "desc"] = "desc"


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def of(cls, items: list[T], *, page: int, page_size: int, total: int) -> "Page[T]":
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max(1, ceil(total / page_size)) if page_size else 1,
        )


class ErrorBody(BaseModel):
    code: str
    message: str
    provider: str | None = None
    capability: str | None = None
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
