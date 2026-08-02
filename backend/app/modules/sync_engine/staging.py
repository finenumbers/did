"""Session-local TEMP staging + atomic cutover into live tables."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import MetaData, Table, insert, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_temp_staging(db: Session, *, live_table: str, stg_table: str) -> Table:
    """
    Create (if needed) a TEMP table with the same columns as live, no constraints.
    ON COMMIT PRESERVE ROWS so staging batches can commit without dropping data.
    """
    db.execute(
        text(
            f"CREATE TEMP TABLE IF NOT EXISTS {stg_table} AS "
            f"SELECT * FROM {live_table} WHERE false"
        )
    )
    db.execute(text(f"TRUNCATE {stg_table}"))
    db.commit()
    meta = MetaData()
    return Table(stg_table, meta, autoload_with=db.connection())


def insert_staging_batches(
    db: Session,
    stg: Table,
    rows: list[dict[str, Any]],
    *,
    batch_size: int = 3000,
    on_progress: Any | None = None,
    progress_label: str = "staging",
) -> int:
    total = len(rows)
    upserted = 0
    if on_progress:
        try:
            on_progress(f"{progress_label} start", 0, total)
        except Exception:
            logger.exception("staging on_progress failed")
    cols = {c.name for c in stg.columns}
    for start in range(0, total, batch_size):
        chunk = [{k: v for k, v in row.items() if k in cols} for row in rows[start : start + batch_size]]
        if chunk:
            db.execute(insert(stg), chunk)
            db.commit()
        upserted += len(chunk)
        if on_progress:
            try:
                on_progress(f"{progress_label} batch", upserted, total)
            except Exception:
                logger.exception("staging on_progress failed")
    return upserted


def cutover_from_staging(
    db: Session,
    *,
    wipe_fn: Any,
    live_raw_table: str | None,
    stg_raw: Table | None,
    live_catalog_table: str,
    stg_catalog: Table,
) -> None:
    """
    One transaction: wipe live slice, copy staging → live, truncate staging.
    On failure before commit, live data is unchanged (txn rollback).
    """
    try:
        wipe_fn()
        if live_raw_table and stg_raw is not None:
            db.execute(
                text(f"INSERT INTO {live_raw_table} SELECT * FROM {stg_raw.name}")
            )
        db.execute(
            text(f"INSERT INTO {live_catalog_table} SELECT * FROM {stg_catalog.name}")
        )
        if stg_raw is not None:
            db.execute(text(f"TRUNCATE {stg_raw.name}"))
        db.execute(text(f"TRUNCATE {stg_catalog.name}"))
        db.commit()
    except Exception:
        db.rollback()
        raise
