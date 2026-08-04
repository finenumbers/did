from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "checkin")
def _unlock_advisory_on_checkin(dbapi_conn, connection_record) -> None:
    """Safety net: never return a connection that still holds session advisory locks."""
    try:
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("SELECT pg_advisory_unlock_all()")
        finally:
            cursor.close()
    except Exception:
        # Broken connection — pool_pre_ping / dispose will handle it.
        pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
