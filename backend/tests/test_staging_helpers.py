"""TEMP staging helpers — clone live columns; insert without reflecting TEMP."""

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, text
from sqlalchemy.orm import Session

from app.modules.sync_engine.locks import CACHE_REFRESH_LOCK_KEY, SYNC_LOCK_KEY
from app.modules.sync_engine.staging import (
    ensure_temp_staging,
    insert_staging_batches,
    staging_table_from_live,
)
from app.modules.sync_engine.service import _exc_summary


def test_lock_keys_distinct():
    assert SYNC_LOCK_KEY != CACHE_REFRESH_LOCK_KEY
    assert isinstance(SYNC_LOCK_KEY, int)


def test_staging_table_from_live_clones_column_names():
    live = Table(
        "sipout_free_numbers_raw",
        MetaData(),
        Column("id", Integer),
        Column("did", String),
        Column("external_key", String),
    )
    stg = staging_table_from_live(live, "sipout_free_numbers_raw_stg")
    assert stg.name == "sipout_free_numbers_raw_stg"
    assert {c.name for c in stg.columns} == {"id", "did", "external_key"}


def test_ensure_temp_staging_insert_without_temp_autoload():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE sipout_free_numbers_raw ("
                "id INTEGER, did VARCHAR, external_key VARCHAR)"
            )
        )

    db = Session(engine)
    try:
        stg = ensure_temp_staging(
            db,
            live_table="sipout_free_numbers_raw",
            stg_table="sipout_free_numbers_raw_stg",
        )
        assert {c.name for c in stg.columns} == {"id", "did", "external_key"}
        n = insert_staging_batches(
            db,
            stg,
            [
                {"id": 1, "did": "74951234567", "external_key": "k1"},
                {"id": 2, "did": "74957654321", "external_key": "k2"},
            ],
            batch_size=1,
        )
        assert n == 2
        count = db.execute(
            text("SELECT COUNT(*) FROM sipout_free_numbers_raw_stg")
        ).scalar_one()
        assert count == 2
    finally:
        db.close()


def test_exc_summary_includes_type_name():
    class NoSuchTableError(Exception):
        pass

    summary = _exc_summary(NoSuchTableError("sipout_free_numbers_raw_stg"))
    assert summary.startswith("NoSuchTableError:")
    assert "sipout_free_numbers_raw_stg" in summary
