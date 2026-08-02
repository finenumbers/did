from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.providers import (
    ProviderHealthOut,
    ProviderOut,
    ProviderSettingsOut,
    ProviderSettingsUpdate,
    TestConnectionOut,
)
from app.services.providers_service import ProvidersService

router = APIRouter(prefix="/providers", tags=["Providers"])


@router.get("", response_model=list[ProviderOut], summary="List providers")
def list_providers(db: Session = Depends(get_db)) -> list[ProviderOut]:
    return ProvidersService(db).list_providers()


@router.get("/health", response_model=list[ProviderHealthOut], tags=["Health"], summary="Providers health")
def health_all(db: Session = Depends(get_db)) -> list[ProviderHealthOut]:
    return ProvidersService(db).health()


@router.get(
    "/{code}/health",
    response_model=list[ProviderHealthOut],
    tags=["Health"],
    summary="Provider health",
)
def health_one(code: str, db: Session = Depends(get_db)) -> list[ProviderHealthOut]:
    return ProvidersService(db).health(code)


@router.get(
    "/{code}/settings",
    response_model=ProviderSettingsOut,
    tags=["Settings"],
    summary="Get provider settings",
)
def get_settings(code: str, db: Session = Depends(get_db)) -> ProviderSettingsOut:
    return ProvidersService(db).get_settings(code)


@router.put(
    "/{code}/settings",
    response_model=ProviderSettingsOut,
    tags=["Settings"],
    summary="Upsert provider settings",
)
def put_settings(
    code: str, payload: ProviderSettingsUpdate, db: Session = Depends(get_db)
) -> ProviderSettingsOut:
    return ProvidersService(db).upsert_settings(code, payload)


@router.patch(
    "/{code}/settings",
    response_model=ProviderSettingsOut,
    tags=["Settings"],
    summary="Patch provider settings",
)
def patch_settings(
    code: str, payload: ProviderSettingsUpdate, db: Session = Depends(get_db)
) -> ProviderSettingsOut:
    return ProvidersService(db).upsert_settings(code, payload)


@router.post(
    "/{code}/test-connection",
    response_model=TestConnectionOut,
    tags=["Settings"],
    summary="Test provider connection",
    description="Runexis: GET api/v1/me. SipOut: balance/get.",
)
async def test_connection(code: str, db: Session = Depends(get_db)) -> TestConnectionOut:
    return await ProvidersService(db).test_connection(code)
