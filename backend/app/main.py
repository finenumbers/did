from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.enums import ProviderCode
from app.models.providers import Provider, ProviderConnection
from app.providers.runexis import contract as runexis_contract
from app.providers.sipout import contract as sipout_contract


def seed_providers() -> None:
    db = SessionLocal()
    try:
        seeds = [
            (ProviderCode.runexis, "Runexis", runexis_contract.EXAMPLE_BASE_URL, {}),
            (ProviderCode.sipout, "SipOut", sipout_contract.EXAMPLE_BASE_URL, {}),
        ]
        for code, name, base_url, auth in seeds:
            existing = db.scalar(select(Provider).where(Provider.code == code))
            if existing:
                continue
            p = Provider(code=code, name=name, is_enabled=True)
            db.add(p)
            db.flush()
            db.add(
                ProviderConnection(
                    provider_id=p.id,
                    base_url=base_url,
                    auth_settings=auth,
                    extra_settings={},
                    is_enabled=True,
                )
            )
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_providers()
    yield


settings = get_settings()
app = FastAPI(
    title="DID Numbering Analytics API",
    description=(
        "Internal telecom numbering analytics. Provider integrations are "
        "documentation-driven from uploaded provider HTML contracts."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}
