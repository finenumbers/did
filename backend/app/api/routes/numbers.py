from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.enums import InventoryKind
from app.schemas.common import Page
from app.schemas.numbers import NumberItem
from app.services.numbers_service import NumbersService

router = APIRouter(prefix="/numbers", tags=["Numbers"])


def _list(
    db: Session,
    kind: InventoryKind,
    page: int,
    page_size: int,
    sort_by: str | None,
    sort_dir: str,
    provider: list[str] | None,
    region: str | None,
    city: str | None,
    status: str | None,
    has_sms: bool | None,
    price_min: Decimal | None,
    price_max: Decimal | None,
    q: str | None,
) -> Page[NumberItem]:
    return NumbersService(db).list_numbers(
        inventory_kind=kind,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        provider=provider,
        region=region,
        city=city,
        status=status,
        has_sms=has_sms,
        price_min=price_min,
        price_max=price_max,
        q=q,
    )


@router.get(
    "/free",
    response_model=Page[NumberItem],
    summary="List free numbers",
    description=(
        "Paginated free inventory from numbers_catalog_normalized. "
        "field_verification marks documentation_verified / example_confirmed / unresolved values."
    ),
)
def list_free(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str | None = Query("last_seen_at"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    provider: list[str] | None = Query(None),
    region: str | None = None,
    city: str | None = None,
    status: str | None = None,
    has_sms: bool | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> Page[NumberItem]:
    return _list(
        db,
        InventoryKind.free,
        page,
        page_size,
        sort_by,
        sort_dir,
        provider,
        region,
        city,
        status,
        has_sms,
        price_min,
        price_max,
        q,
    )


@router.get(
    "/purchased",
    response_model=Page[NumberItem],
    summary="List purchased numbers",
    description="Paginated purchased inventory. SipOut source action: did/connected_list.",
)
def list_purchased(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str | None = Query("last_seen_at"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    provider: list[str] | None = Query(None),
    region: str | None = None,
    city: str | None = None,
    status: str | None = None,
    has_sms: bool | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> Page[NumberItem]:
    return _list(
        db,
        InventoryKind.purchased,
        page,
        page_size,
        sort_by,
        sort_dir,
        provider,
        region,
        city,
        status,
        has_sms,
        price_min,
        price_max,
        q,
    )
