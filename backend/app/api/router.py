from fastapi import APIRouter

from app.api.routes import auth, numbers, providers, pstn_inn_cache, sync

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(numbers.router)
api_router.include_router(providers.router)
api_router.include_router(pstn_inn_cache.router)
api_router.include_router(sync.router)
