"""Overwriteable sync debug log file (flushed after every write)."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_current: SyncRunFileLogger | None = None

_HANDLER_LOGGER_NAMES = (
    "app.modules.sync_engine",
    "app.providers",
)


def sync_debug_log_path() -> Path:
    return Path(get_settings().sync_debug_log_path)


def sync_debug_log_exists() -> bool:
    path = sync_debug_log_path()
    return path.is_file() and path.stat().st_size > 0


def get_sync_debug_log() -> SyncRunFileLogger | None:
    return _current


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class _SyncFileLogHandler(logging.Handler):
    """Mirror process logs into the active sync debug file."""

    def __init__(self, file_logger: SyncRunFileLogger) -> None:
        super().__init__(level=logging.INFO)
        self._file_logger = file_logger

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name == "app.modules.sync_engine.run_file_log":
                return
            msg = self.format(record)
            self._file_logger.write(record.levelname, f"[py:{record.name}] {msg}")
        except Exception:
            self.handleError(record)


class SyncRunFileLogger:
    def __init__(self, path: Path, run_id: UUID) -> None:
        self.path = path
        self.run_id = run_id
        self._fp: Any | None = None
        self._handler: _SyncFileLogHandler | None = None
        self._attached: list[logging.Logger] = []

    def open(self, *, triggered_by: str | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.path, "w", encoding="utf-8")  # truncate previous sync
        self.write(
            "INFO",
            f"=== SYNC DEBUG LOG START run_id={self.run_id} "
            f"triggered_by={triggered_by or '-'} ===",
        )
        self._attach_handlers()

    def _attach_handlers(self) -> None:
        handler = _SyncFileLogHandler(self)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._handler = handler
        for name in _HANDLER_LOGGER_NAMES:
            lg = logging.getLogger(name)
            lg.addHandler(handler)
            self._attached.append(lg)

    def _detach_handlers(self) -> None:
        if self._handler is None:
            return
        for lg in self._attached:
            try:
                lg.removeHandler(self._handler)
            except Exception:
                pass
        self._attached.clear()
        self._handler = None

    def write(self, level: str, message: str) -> None:
        with _lock:
            if self._fp is None or self._fp.closed:
                return
            line = f"{_ts()}  {level.upper():7}  {message.rstrip()}\n"
            self._fp.write(line)
            self._fp.flush()
            try:
                os.fsync(self._fp.fileno())
            except OSError:
                pass

    def stage_begin(self, stage_id: str, detail: str = "") -> None:
        extra = f" detail={detail!r}" if detail else ""
        self.write("INFO", f"=== BEGIN {stage_id} ==={extra}")

    def stage_progress(
        self,
        stage_id: str,
        *,
        detail: str | None = None,
        substage: str | None = None,
        current: int | None = None,
        total: int | None = None,
        unit: str = "",
    ) -> None:
        parts = [f"[progress] {stage_id}"]
        if detail is not None:
            parts.append(f"detail={detail!r}")
        if substage:
            parts.append(f"substage={substage!r}")
        if current is not None:
            parts.append(f"current={current}")
        if total is not None:
            parts.append(f"total={total}")
        if unit:
            parts.append(f"unit={unit!r}")
        self.write("INFO", " ".join(parts))

    def stage_end(self, stage_id: str, detail: str = "", *, status: str = "done") -> None:
        extra = f" detail={detail!r}" if detail else ""
        self.write("INFO", f"=== END {stage_id} status={status} ==={extra}")

    def close(self, *, status: str | None = None, error_summary: str | None = None) -> None:
        with _lock:
            try:
                if self._fp is not None and not self._fp.closed:
                    self.write(
                        "INFO",
                        f"=== SYNC DEBUG LOG END run_id={self.run_id} "
                        f"status={status or '-'} error={error_summary or '-'} ===",
                    )
            finally:
                self._detach_handlers()
                if self._fp is not None and not self._fp.closed:
                    try:
                        self._fp.close()
                    except Exception:
                        logger.exception("Failed to close sync debug log")
                self._fp = None


def begin_sync_debug_log(
    run_id: UUID, *, triggered_by: str | None = None
) -> SyncRunFileLogger:
    global _current
    with _lock:
        if _current is not None:
            try:
                _current.close(status="superseded")
            except Exception:
                logger.exception("Failed to close previous sync debug log")
            _current = None
        fl = SyncRunFileLogger(sync_debug_log_path(), run_id)
        fl.open(triggered_by=triggered_by)
        _current = fl
        return fl


def end_sync_debug_log(
    *, status: str | None = None, error_summary: str | None = None
) -> None:
    global _current
    with _lock:
        if _current is None:
            return
        try:
            _current.close(status=status, error_summary=error_summary)
        finally:
            _current = None


def mirror_db_log(level: str, message: str, *, source: str = "db") -> None:
    fl = get_sync_debug_log()
    if fl is None:
        return
    fl.write(level, f"[{source}] {message}")
