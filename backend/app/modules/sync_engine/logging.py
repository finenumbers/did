from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import SyncLogLevel
from app.models.sync import SyncJobLog
from app.modules.sync_engine.run_file_log import mirror_db_log


def log_job(
    db: Session,
    job_id: uuid.UUID,
    level: SyncLogLevel,
    message: str,
    context: dict[str, Any] | None = None,
) -> None:
    db.add(
        SyncJobLog(
            sync_job_id=job_id,
            level=level,
            message=message,
            context=context or {},
        )
    )
    db.flush()
    mirror_db_log(level.value, message, source="job", context=context)
