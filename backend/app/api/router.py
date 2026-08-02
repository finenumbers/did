from fastapi import APIRouter

from app.api.routes import numbers, providers, sync

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(numbers.router)
api_router.include_router(providers.router)
api_router.include_router(sync.router)
