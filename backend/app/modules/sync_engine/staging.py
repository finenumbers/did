"""Session-local TEMP staging + atomic cutover into live tables."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Column, MetaData, Table, insert, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def staging_table_from_live(live: Table, stg_table: str) -> Table:
    """
    Build an in-memory Table for INSERT into a TEMP staging relation.

    Do not autoload TEMP tables: Postgres keeps them in a session-private
    pg_temp_* schema and SQLAlchemy reflection often raises NoSuchTableError
    with only the bare table name as the message.
    """
    cols = [Column(c.name, c.type, nullable=c.nullable) for c in live.columns]
    return Table(stg_table, MetaData(), *cols)


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
    # DELETE (not TRUNCATE): empty TEMP is cheap; works on Postgres and SQLite tests.
    db.execute(text(f"DELETE FROM {stg_table}"))
    db.commit()
    live = Table(live_table, MetaData(), autoload_with=db.connection())
    return staging_table_from_live(live, stg_table)


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
