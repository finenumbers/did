from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()
# Single backend replica: one connection may be held for the whole sync (advisory lock).
# Leave headroom for API/facets/export while sync runs (~25–40 min).
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Dedicated engine for long-held advisory locks. NullPool: connections never share the
# main pool checkin path (which runs pg_advisory_unlock_all).
_lock_connect_args: dict = {}
if settings.database_url.startswith("postgresql"):
    _lock_connect_args = {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }

lock_engine = create_engine(
    settings.database_url,
    poolclass=NullPool,
    pool_pre_ping=True,
    connect_args=_lock_connect_args,
)


@event.listens_for(engine, "checkin")
def _clear_advisory_locks_on_checkin(dbapi_conn, _connection_record) -> None:
    """Never return a main-pool connection while holding session advisory locks."""
    if engine.dialect.name != "postgresql":
        return
    from app.modules.sync_engine.locks import clear_advisory_locks_dbapi

    clear_advisory_locks_dbapi(dbapi_conn)


def dispose_engine_pool() -> None:
    """Drop main pooled connections (releases leaked session advisory locks on main pool).

    Does not dispose lock_engine — never call this while a sync lock Connection is held
    unless the caller has already closed that connection.
    """
    engine.dispose()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
