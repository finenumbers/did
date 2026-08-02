"""Logging helpers for unified sync runs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import SyncLogLevel
from app.models.sync import SyncRunLog


def log_run(
    db: Session,
    run_id: uuid.UUID,
    level: SyncLogLevel | str,
    message: str,
    context: dict[str, Any] | None = None,
) -> None:
    if isinstance(level, str):
        level = SyncLogLevel(level)
    db.add(
        SyncRunLog(
            sync_run_id=run_id,
            level=level,
            message=message,
            context=context or {},
        )
    )
    db.commit()
