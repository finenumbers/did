"""Idempotent Aurora settings backfill: legacy base_url → extra_settings.csv_files."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.enums import ProviderCode
from app.models.providers import Provider
from app.providers.aurora import contract

logger = logging.getLogger(__name__)


def backfill_aurora_csv_files(db: Session) -> bool:
    """
    If Aurora connection has empty csv_files, populate from legacy base_url once.

    Returns True when a write was performed.
    """
    provider = db.scalar(select(Provider).where(Provider.code == ProviderCode.aurora))
    if provider is None or provider.connection is None:
        return False
    conn = provider.connection
    extra = dict(conn.extra_settings or {})
    if contract.csv_files_configured(extra):
        return False
    entries = contract.legacy_backfill_entries(conn.base_url)
    extra["csv_files"] = [e.to_dict() for e in entries]
    conn.extra_settings = extra
    flag_modified(conn, "extra_settings")
    # base_url no longer drives sync; clear to avoid misleading Settings display.
    conn.base_url = None
    db.commit()
    logger.warning(
        "Aurora csv_files backfilled count=%s from legacy base_url",
        len(entries),
    )
    return True
