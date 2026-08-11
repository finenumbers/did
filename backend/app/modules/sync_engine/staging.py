"""Persistent UNLOGGED staging + atomic cutover into live tables.

TEMP tables are unsafe with SQLAlchemy connection pooling: CREATE TEMP on one
checkout can disappear before INSERT after commit/reconnect (UndefinedTable).
Staging tables live in the normal schema; unified sync holds an advisory lock
so only one writer uses them at a time.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Column, MetaData, Table, insert, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def staging_table_from_live(live: Table, stg_table: str) -> Table:
    """In-memory Table for INSERT into a staging relation (column list from live)."""
    cols = [Column(c.name, c.type, nullable=c.nullable) for c in live.columns]
    return Table(stg_table, MetaData(), *cols)


def ensure_temp_staging(db: Session, *, live_table: str, stg_table: str) -> Table:
    """
    Ensure a durable staging table with the same columns as live (no constraints),
    then clear it for this run.

    Name kept as ensure_temp_staging for call-site compatibility; storage is
    UNLOGGED (Postgres) / plain table (SQLite), not TEMP.
    """
    bind = db.get_bind()
    dialect = bind.dialect.name
    # Always recreate from current live schema to avoid column drift vs SELECT *
    db.execute(text(f"DROP TABLE IF EXISTS {stg_table}"))
    if dialect == "postgresql":
        db.execute(
            text(
                f"CREATE UNLOGGED TABLE {stg_table} AS "
                f"SELECT * FROM {live_table} WHERE false"
            )
        )
    else:
        db.execute(
            text(
                f"CREATE TABLE {stg_table} AS "
                f"SELECT * FROM {live_table} WHERE false"
            )
        )
    db.commit()
    live = Table(live_table, MetaData(), autoload_with=db.connection())
    return staging_table_from_live(live, stg_table)


def insert_staging_batches(
    db: Session,
    stg: Table,
    rows: list[dict[str, Any]],
    *,
    batch_size: int = 8000,
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
