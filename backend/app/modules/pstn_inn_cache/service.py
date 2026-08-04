"""PSTN INN ranges cache service (Contour B — operator column only)."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.db import SessionLocal
from app.models.enums import ProviderCode
from app.models.providers import Provider, SystemSetting
from app.models.pstn_cache import PstnInnCacheOperator, PstnInnRangeCache
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderError
from app.providers.finenumbers.client import FinenumbersClient

logger = logging.getLogger(__name__)

REQUIRED_OPERATORS: list[tuple[str, str]] = [
    ("ООО «СИПАУТНЭТ»", "5920032027"),
    ("ООО «ИНТЕРНОД»", "7733808377"),
    ("ООО «Фронтир Нетворк»", "5406978329"),
    ("ООО «НОВОСИСТЕМ»", "7710311878"),
    ("ООО «Аврора Телеком»", "7810833282"),
    ("АО «ЭР-Телеком Холдинг»", "5902202276"),
]
REQUIRED_INNS: frozenset[str] = frozenset(inn for _, inn in REQUIRED_OPERATORS)

INN_RE = re.compile(r"^\d{10}(\d{2})?$")
REFRESH_SETTING_KEY = "pstn_inn_cache_refresh"
_refresh_lock = threading.Lock()
_refresh_thread: threading.Thread | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_inn(inn: str) -> str:
    value = (inn or "").strip()
    if not INN_RE.match(value):
        raise ProviderError("ИНН должен содержать 10 или 12 цифр", code="INVALID_INN")
    return value


def ensure_required_operators(db: Session) -> None:
    existing = {
        row.inn: row
        for row in db.scalars(select(PstnInnCacheOperator)).all()
    }
    changed = False
    for name, inn in REQUIRED_OPERATORS:
        row = existing.get(inn)
        if row is None:
            db.add(
                PstnInnCacheOperator(
                    name=name,
                    inn=inn,
                    enabled=True,
                    required=True,
                    ranges_count=0,
                )
            )
            changed = True
        else:
            if not row.required or not row.enabled or row.name != name:
                row.required = True
                row.enabled = True
                if not row.name:
                    row.name = name
                changed = True
    if changed:
        db.commit()


def is_operator_ready(op: PstnInnCacheOperator) -> bool:
    return bool(op.enabled and op.ranges_count > 0 and not (op.last_error and op.ranges_count == 0))


def is_min_cache_ready(db: Session) -> bool:
    ensure_required_operators(db)
    rows = db.scalars(
        select(PstnInnCacheOperator).where(PstnInnCacheOperator.inn.in_(REQUIRED_INNS))
    ).all()
    by_inn = {r.inn: r for r in rows}
    for inn in REQUIRED_INNS:
        op = by_inn.get(inn)
        if op is None or not is_operator_ready(op):
            return False
    return True


def missing_required_inns(db: Session) -> list[str]:
    ensure_required_operators(db)
    rows = db.scalars(
        select(PstnInnCacheOperator).where(PstnInnCacheOperator.inn.in_(REQUIRED_INNS))
    ).all()
    by_inn = {r.inn: r for r in rows}
    missing: list[str] = []
    for name, inn in REQUIRED_OPERATORS:
        op = by_inn.get(inn)
        if op is None or not is_operator_ready(op):
            missing.append(f"{name} ({inn})")
    return missing


def _get_or_create_setting(db: Session, key: str, default: dict) -> SystemSetting:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        row = SystemSetting(key=key, value=dict(default), description=None, is_secret=False)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_refresh_status(db: Session) -> dict[str, Any]:
    row = _get_or_create_setting(
        db,
        REFRESH_SETTING_KEY,
        {"status": "idle", "detail": "", "started_at": None, "finished_at": None, "error": None},
    )
    return dict(row.value or {})


def is_refresh_running(db: Session) -> bool:
    status = get_refresh_status(db).get("status")
    return status in {"pending", "running"}


def mark_refresh_interrupted(db: Session) -> None:
    status = get_refresh_status(db).get("status")
    if status in {"pending", "running"}:
        _set_refresh_status(
            db,
            status="failed",
            detail="Interrupted by server restart",
            finished_at=_now().isoformat(),
            error="Interrupted by server restart",
        )


def _set_refresh_status(db: Session, **patch: Any) -> dict[str, Any]:
    row = _get_or_create_setting(
        db,
        REFRESH_SETTING_KEY,
        {"status": "idle", "detail": "", "started_at": None, "finished_at": None, "error": None},
    )
    value = dict(row.value or {})
    value.update(patch)
    row.value = value
    flag_modified(row, "value")
    db.commit()
    return value


def _numbers_count_by_inn(db: Session) -> dict[str, int]:
    """Total MSISDNs covered by cached ranges per INN (sum of range sizes)."""
    rows = db.execute(
        select(
            PstnInnRangeCache.inn,
            func.coalesce(
                func.sum(PstnInnRangeCache.range_end - PstnInnRangeCache.range_start + 1),
                0,
            ),
        ).group_by(PstnInnRangeCache.inn)
    ).all()
    return {str(inn): int(total or 0) for inn, total in rows}


def get_cache_status(db: Session) -> dict[str, Any]:
    ensure_required_operators(db)
    ops = db.scalars(
        select(PstnInnCacheOperator).order_by(
            PstnInnCacheOperator.required.desc(),
            PstnInnCacheOperator.name.asc(),
        )
    ).all()
    missing = missing_required_inns(db)
    numbers_by_inn = _numbers_count_by_inn(db)
    return {
        "min_cache_ready": len(missing) == 0,
        "missing_required": missing,
        "refresh": get_refresh_status(db),
        "operators": [
            {
                "id": str(op.id),
                "name": op.name,
                "inn": op.inn,
                "enabled": op.enabled,
                "required": op.required,
                "ranges_count": op.ranges_count,
                "numbers_count": numbers_by_inn.get(op.inn, 0),
                "last_synced_at": op.last_synced_at.isoformat() if op.last_synced_at else None,
                "last_error": op.last_error,
            }
            for op in ops
        ],
    }


def add_operator(db: Session, *, name: str, inn: str, enabled: bool = True) -> PstnInnCacheOperator:
    inn = validate_inn(inn)
    name = (name or "").strip()
    if not name:
        raise ProviderError("Укажите название оператора", code="INVALID_OPERATOR_NAME")
    existing = db.scalar(select(PstnInnCacheOperator).where(PstnInnCacheOperator.inn == inn))
    if existing:
        raise ProviderError(f"Оператор с ИНН {inn} уже есть", code="OPERATOR_INN_EXISTS")
    op = PstnInnCacheOperator(
        name=name,
        inn=inn,
        enabled=enabled,
        required=inn in REQUIRED_INNS,
        ranges_count=0,
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def update_operator(
    db: Session,
    inn: str,
    *,
    name: str | None = None,
    enabled: bool | None = None,
) -> PstnInnCacheOperator:
    inn = validate_inn(inn)
    op = db.scalar(select(PstnInnCacheOperator).where(PstnInnCacheOperator.inn == inn))
    if op is None:
        raise ProviderError("Оператор не найден", code="OPERATOR_NOT_FOUND")
    if op.required or inn in REQUIRED_INNS:
        op.required = True
        if enabled is False:
            raise ProviderError(
                "Обязательного оператора нельзя выключить",
                code="REQUIRED_OPERATOR_LOCKED",
            )
        op.enabled = True
    elif enabled is not None:
        op.enabled = enabled
    if name is not None:
        name = name.strip()
        if not name:
            raise ProviderError("Укажите название оператора", code="INVALID_OPERATOR_NAME")
        op.name = name
    db.commit()
    db.refresh(op)
    return op


def delete_operator(db: Session, inn: str) -> None:
    inn = validate_inn(inn)
    if inn in REQUIRED_INNS:
        raise ProviderError(
            "Обязательного оператора нельзя удалить",
            code="REQUIRED_OPERATOR_LOCKED",
        )
    op = db.scalar(select(PstnInnCacheOperator).where(PstnInnCacheOperator.inn == inn))
    if op is None:
        raise ProviderError("Оператор не найден", code="OPERATOR_NOT_FOUND")
    if op.required:
        raise ProviderError(
            "Обязательного оператора нельзя удалить",
            code="REQUIRED_OPERATOR_LOCKED",
        )
    db.execute(delete(PstnInnRangeCache).where(PstnInnRangeCache.inn == inn))
    db.delete(op)
    db.commit()


def _finenumbers_connection(db: Session) -> ConnectionConfig:
    provider = db.scalars(
        select(Provider)
        .options(joinedload(Provider.connection))
        .where(Provider.code == ProviderCode.finenumbers)
    ).first()
    if provider is None or provider.connection is None:
        raise ProviderError(
            "Нет подключения Finenumbers (PSTN API)",
            code="FINENUMBERS_CONNECTION_MISSING",
        )
    conn = provider.connection
    auth = dict(conn.auth_settings or {})
    if not auth.get("key"):
        raise ProviderError(
            "В настройках Finenumbers не задан API key",
            code="FINENUMBERS_API_KEY_MISSING",
        )
    return ConnectionConfig(
        base_url=conn.base_url,
        auth_settings=auth,
        extra_settings=dict(conn.extra_settings or {}),
    )


def load_enabled_ranges_for_enrich(db: Session) -> list[dict[str, Any]]:
    """Load ranges for enabled operators. Used only to fill catalog.operator."""
    enabled_inns = db.scalars(
        select(PstnInnCacheOperator.inn).where(PstnInnCacheOperator.enabled.is_(True))
    ).all()
    if not enabled_inns:
        return []
    rows = db.scalars(
        select(PstnInnRangeCache).where(PstnInnRangeCache.inn.in_(list(enabled_inns)))
    ).all()
    # Contour B: expose only fields needed for operator match (region ignored by enrich)
    return [
        {
            "abc": r.abc,
            "rangeStart": r.range_start,
            "rangeEnd": r.range_end,
            "operator": r.operator,
        }
        for r in rows
        if r.operator
    ]


async def refresh_enabled_caches(db: Session) -> dict[str, Any]:
    """Manual refresh: replace ranges for each enabled operator via PSTN by-inn."""
    ensure_required_operators(db)
    connection = _finenumbers_connection(db)
    ops = db.scalars(
        select(PstnInnCacheOperator).where(PstnInnCacheOperator.enabled.is_(True))
    ).all()
    if not ops:
        raise ProviderError("Нет включённых операторов для загрузки кеша", code="NO_ENABLED_OPERATORS")

    _set_refresh_status(
        db,
        status="running",
        detail="Загрузка кеша…",
        started_at=_now().isoformat(),
        finished_at=None,
        error=None,
    )

    client = FinenumbersClient(connection)
    results: list[dict[str, Any]] = []
    try:
        for idx, op in enumerate(ops, start=1):
            _set_refresh_status(
                db,
                status="running",
                detail=f"{op.name} ({op.inn}) — {idx}/{len(ops)}",
            )
            try:
                from app.modules.sync_engine.safety import reload_allowed

                ranges, _ = await client.iter_all_ranges_by_inn(inn=op.inn)
                synced_at = _now()
                staged: list[dict[str, Any]] = []
                for row in ranges:
                    abc = str(row.get("abc") or "").strip()
                    operator = str(row.get("operator") or "").strip()
                    region = str(row.get("region") or "").strip() or None
                    try:
                        start = int(row["rangeStart"])
                        end = int(row["rangeEnd"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if not abc or not operator or end < start:
                        continue
                    staged.append(
                        {
                            "id": uuid4(),
                            "inn": op.inn,
                            "abc": abc,
                            "range_start": start,
                            "range_end": end,
                            "operator": operator,
                            "region": region,
                            "synced_at": synced_at,
                        }
                    )
                previous = int(op.ranges_count or 0)
                incoming = len(staged)
                ok, reason = reload_allowed(
                    previous=previous, incoming=incoming, kind="free"
                )
                if not ok:
                    op.last_error = reason or "PSTN вернул недостаточно диапазонов"
                    db.commit()
                    results.append(
                        {
                            "inn": op.inn,
                            "name": op.name,
                            "ranges_count": previous,
                            "incoming": incoming,
                            "ok": False,
                            "error": op.last_error,
                        }
                    )
                    continue

                # Atomic swap for this INN: wipe old only after staging validated
                db.execute(delete(PstnInnRangeCache).where(PstnInnRangeCache.inn == op.inn))
                for item in staged:
                    db.add(PstnInnRangeCache(**item))
                op.ranges_count = incoming
                op.last_synced_at = synced_at
                op.last_error = None
                db.commit()
                results.append(
                    {
                        "inn": op.inn,
                        "name": op.name,
                        "ranges_count": incoming,
                        "ok": True,
                    }
                )
            except Exception as exc:
                logger.exception("Failed to refresh INN cache for %s", op.inn)
                db.rollback()
                op = db.get(PstnInnCacheOperator, op.id) or op
                op.last_error = str(exc)[:500]
                db.commit()
                results.append(
                    {
                        "inn": op.inn,
                        "name": op.name,
                        "ranges_count": op.ranges_count,
                        "ok": False,
                        "error": str(exc)[:300],
                    }
                )
    finally:
        await client.aclose()

    ready = is_min_cache_ready(db)
    failed = [r for r in results if not r.get("ok")]
    error = None
    if failed:
        error = "; ".join(
            f"{r['name']}: {r.get('error') or '0 ranges'}" for r in failed
        )[:500]
    _set_refresh_status(
        db,
        status="failed" if not ready else "success",
        detail=f"Готово. min_cache_ready={ready}",
        finished_at=_now().isoformat(),
        error=error,
        results=results,
    )
    return {"min_cache_ready": ready, "results": results, "error": error}


def spawn_cache_refresh() -> None:
    """Run cache refresh in a daemon thread (manual Settings action only)."""
    global _refresh_thread
    with _refresh_lock:
        if _refresh_thread is not None and _refresh_thread.is_alive():
            raise ProviderError(
                "Загрузка кеша уже выполняется",
                code="PSTN_INN_CACHE_REFRESH_RUNNING",
            )
        db = SessionLocal()
        try:
            from app.modules.sync_engine.unified import get_active_run

            if get_active_run(db) is not None:
                raise ProviderError(
                    "Нельзя загружать кеш во время синхронизации",
                    code="SYNC_ALREADY_RUNNING",
                )
            if _refresh_thread is not None and _refresh_thread.is_alive():
                raise ProviderError(
                    "Загрузка кеша уже выполняется",
                    code="PSTN_INN_CACHE_REFRESH_RUNNING",
                )
            _set_refresh_status(
                db,
                status="pending",
                detail="Ожидание…",
                started_at=_now().isoformat(),
                finished_at=None,
                error=None,
            )
        finally:
            db.close()

        def _runner() -> None:
            from app.modules.sync_engine.locks import (
                CACHE_REFRESH_LOCK_KEY,
                advisory_unlock,
                try_advisory_lock,
            )

            session = SessionLocal()
            locked = False
            try:
                if not try_advisory_lock(session, CACHE_REFRESH_LOCK_KEY):
                    _set_refresh_status(
                        session,
                        status="failed",
                        detail="Загрузка кеша уже выполняется (lock)",
                        finished_at=_now().isoformat(),
                        error="PSTN_INN_CACHE_REFRESH_RUNNING",
                    )
                    return
                locked = True
                session.commit()
                asyncio.run(refresh_enabled_caches(session))
            except Exception as exc:
                logger.exception("Cache refresh crashed")
                try:
                    session.rollback()
                    _set_refresh_status(
                        session,
                        status="failed",
                        detail="Сбой загрузки кеша",
                        finished_at=_now().isoformat(),
                        error=str(exc)[:500],
                    )
                except Exception:
                    session.rollback()
            finally:
                if locked:
                    try:
                        advisory_unlock(session, CACHE_REFRESH_LOCK_KEY)
                    except Exception:
                        pass
                session.close()

        _refresh_thread = threading.Thread(target=_runner, name="pstn-inn-cache-refresh", daemon=True)
        _refresh_thread.start()


def get_sync_schedule(db: Session) -> dict[str, Any]:
    row = _get_or_create_setting(
        db,
        "sync_schedule",
        {"enabled": False, "timezone": "Europe/Moscow", "hour": 21, "minute": 0},
    )
    value = dict(row.value or {})
    value.setdefault("enabled", False)
    value.setdefault("timezone", "Europe/Moscow")
    value.setdefault("hour", 21)
    value.setdefault("minute", 0)
    return value


def set_sync_schedule(db: Session, *, enabled: bool) -> dict[str, Any]:
    row = _get_or_create_setting(
        db,
        "sync_schedule",
        {"enabled": False, "timezone": "Europe/Moscow", "hour": 21, "minute": 0},
    )
    value = dict(row.value or {})
    value["enabled"] = bool(enabled)
    value.setdefault("timezone", "Europe/Moscow")
    value.setdefault("hour", 21)
    value.setdefault("minute", 0)
    row.value = value
    flag_modified(row, "value")
    db.commit()
    return value


def require_min_cache_ready(db: Session) -> None:
    if is_refresh_running(db):
        raise ProviderError(
            "Дождитесь окончания загрузки кеша операторов",
            code="PSTN_INN_CACHE_REFRESH_RUNNING",
        )
    if not is_min_cache_ready(db):
        missing = missing_required_inns(db)
        raise ProviderError(
            "Сначала загрузите кеш операторов в Настройках "
            f"(не готово: {', '.join(missing)})",
            code="PSTN_INN_CACHE_NOT_READY",
            details={"missing_required": missing},
        )
