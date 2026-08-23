import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.auth import AdminAuthMiddleware
from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import auth_enabled
from app.models.enums import ProviderCode, SyncJobStatus
from app.models.providers import Provider, ProviderConnection
from app.models.sync import SyncRun
from app.modules.pstn_inn_cache.service import ensure_required_operators
from app.modules.sync_engine.scheduler import sync_schedule_loop
from app.providers.aurora import contract as aurora_contract
from app.providers.didww import contract as didww_contract
from app.providers.exolve import contract as exolve_contract
from app.providers.voximplant import contract as voximplant_contract
from app.providers.mcn import contract as mcn_contract
from app.providers.finenumbers import contract as finenumbers_contract
from app.providers.runexis import contract as runexis_contract
from app.providers.sipout import contract as sipout_contract
from app.providers.uis import contract as uis_contract


def mark_interrupted_runs() -> None:
    """Background sync dies with the process; clear orphaned active runs on boot."""
    from app.modules.sync_engine.progress import apply_progress_abort

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(SyncRun).where(
                SyncRun.status.in_((SyncJobStatus.pending, SyncJobStatus.running))
            )
        ).all()
        now = datetime.now(timezone.utc)
        reason = "Interrupted by server restart"
        for run in rows:
            run.status = SyncJobStatus.failed
            run.error_summary = reason
            run.finished_at = now
            apply_progress_abort(run, reason)
        if rows:
            db.commit()
        from app.modules.pstn_inn_cache.service import mark_refresh_interrupted

        mark_refresh_interrupted(db)
    finally:
        db.close()


def seed_providers() -> None:
    db = SessionLocal()
    try:
        seeds: list[tuple] = [
            (ProviderCode.runexis, "Runexis", runexis_contract.EXAMPLE_BASE_URL, {}, {}),
            (ProviderCode.sipout, "SipOut", sipout_contract.EXAMPLE_BASE_URL, {}, {}),
            (
                ProviderCode.finenumbers,
                "Finenumbers",
                finenumbers_contract.EXAMPLE_BASE_URL,
                {},
                {},
            ),
            (ProviderCode.uis, "UIS", uis_contract.EXAMPLE_BASE_URL, {}, {}),
            (
                ProviderCode.aurora,
                "Aurora Telecom",
                None,
                {},
                {"csv_files": [e.to_dict() for e in aurora_contract.seed_csv_files()]},
            ),
            (ProviderCode.exolve, "Exolve", exolve_contract.EXAMPLE_BASE_URL, {}, {}),
            (
                ProviderCode.voximplant,
                "Voximplant",
                voximplant_contract.EXAMPLE_BASE_URL,
                {},
                {},
            ),
            (
                ProviderCode.mcn,
                "MCN Telecom",
                mcn_contract.EXAMPLE_BASE_URL,
                {},
                {},
            ),
            (
                ProviderCode.didww,
                "DIDWW",
                didww_contract.EXAMPLE_BASE_URL,
                {},
                {},
            ),
        ]
        for code, name, base_url, auth, extra in seeds:
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
                    extra_settings=extra,
                    is_enabled=True,
                )
            )
        db.commit()
    finally:
        db.close()


def backfill_aurora_settings() -> None:
    db = SessionLocal()
    try:
        from app.providers.aurora.backfill import backfill_aurora_csv_files

        backfill_aurora_csv_files(db)
    finally:
        db.close()


def seed_pstn_inn_cache_operators() -> None:
    db = SessionLocal()
    try:
        ensure_required_operators(db)
    finally:
        db.close()


def seed_mask_types() -> None:
    db = SessionLocal()
    try:
        from app.services.mask_types_service import ensure_mask_types_seeded

        ensure_mask_types_seeded(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_providers()
    backfill_aurora_settings()
    seed_pstn_inn_cache_operators()
    seed_mask_types()
    mark_interrupted_runs()
    schedule_task = asyncio.create_task(sync_schedule_loop())
    try:
        yield
    finally:
        schedule_task.cancel()
        try:
            await schedule_task
        except asyncio.CancelledError:
            pass


settings = get_settings()
if settings.did_require_auth and not auth_enabled():
    raise SystemExit(
        "DID_REQUIRE_AUTH is set but ADMIN_USERNAME/ADMIN_PASSWORD are missing. "
        "Login credentials are required (ADMIN_API_TOKEN alone is not enough)."
    )

_hide_docs = settings.did_require_auth
app = FastAPI(
    title="DID Numbering Analytics API",
    description=(
        "Internal telecom numbering analytics. Provider integrations are "
        "documentation-driven from uploaded provider HTML contracts."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _hide_docs else "/docs",
    redoc_url=None if _hide_docs else "/redoc",
    openapi_url=None if _hide_docs else "/openapi.json",
)
register_exception_handlers(app)
app.add_middleware(AdminAuthMiddleware)
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
