from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

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


@event.listens_for(engine, "checkin")
def _clear_advisory_locks_on_checkin(dbapi_conn, _connection_record) -> None:
    """Never return a connection to the pool while holding session advisory locks."""
    if engine.dialect.name != "postgresql":
        return
    from app.modules.sync_engine.locks import clear_advisory_locks_dbapi

    clear_advisory_locks_dbapi(dbapi_conn)


def dispose_engine_pool() -> None:
    """Drop all pooled connections (releases any leaked session advisory locks)."""
    engine.dispose()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
