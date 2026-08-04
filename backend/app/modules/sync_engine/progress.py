"""Stage plan + progress tracker for unified sync runs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.sync import SyncRun
from app.modules.sync_engine.run_file_log import get_sync_debug_log

STAGE_DEFS: list[dict[str, str]] = [
    {"id": "prepare", "group": "Общее", "label": "Подготовка"},
    {"id": "sipout_dictionaries", "group": "SipOut", "label": "Справочники"},
    {"id": "sipout_free", "group": "SipOut", "label": "Свободные номера"},
    {"id": "sipout_purchased", "group": "SipOut", "label": "Купленные номера"},
    {"id": "runexis_dictionaries", "group": "Runexis", "label": "Справочники"},
    {"id": "runexis_free", "group": "Runexis", "label": "Свободные номера"},
    {"id": "runexis_purchased", "group": "Runexis", "label": "Купленные номера"},
    {"id": "uis_free", "group": "UIS", "label": "Свободные номера"},
    {"id": "uis_purchased", "group": "UIS", "label": "Купленные номера"},
    {"id": "aurora_free", "group": "Aurora Telecom", "label": "Свободные номера"},
    {"id": "finenumbers_free", "group": "Finenumbers", "label": "Свободные номера"},
    {"id": "operator_enrichment", "group": "Общее", "label": "Обогащение операторов"},
    {"id": "finalize", "group": "Общее", "label": "Завершение"},
]

_PHASE_STAGE: dict[tuple[str, str], str] = {
    ("sipout", "dictionaries"): "sipout_dictionaries",
    ("sipout", "free"): "sipout_free",
    ("sipout", "purchased"): "sipout_purchased",
    ("runexis", "dictionaries"): "runexis_dictionaries",
    ("runexis", "free"): "runexis_free",
    ("runexis", "purchased"): "runexis_purchased",
    ("uis", "free"): "uis_free",
    ("uis", "purchased"): "uis_purchased",
    ("aurora", "free"): "aurora_free",
    ("finenumbers", "free"): "finenumbers_free",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_initial_progress() -> dict[str, Any]:
    stages = [
        {
            "id": s["id"],
            "group": s["group"],
            "label": s["label"],
            "status": "pending",
            "detail": "",
            "substage": "",
            "progress": {"current": None, "total": None, "unit": ""},
            "started_at": None,
            "finished_at": None,
        }
        for s in STAGE_DEFS
    ]
    return {"current_stage_id": "prepare", "stages": stages}


def stage_for_provider_phase(provider_code: str, phase: str) -> str | None:
    return _PHASE_STAGE.get((provider_code, phase))


def stage_status(progress: dict[str, Any] | None, stage_id: str) -> str | None:
    if not progress:
        return None
    for stage in progress.get("stages") or []:
        if stage.get("id") == stage_id:
            return stage.get("status")
    return None


class SyncProgressTracker:
    def __init__(self, db: Session, run_id: UUID):
        self.db = db
        self.run_id = run_id

    def _load(self) -> SyncRun:
        run = self.db.get(SyncRun, self.run_id)
        if not run:
            raise RuntimeError(f"SyncRun not found: {self.run_id}")
        if not run.progress:
            run.progress = build_initial_progress()
        return run

    def _save(self, run: SyncRun) -> None:
        flag_modified(run, "progress")
        self.db.commit()

    def _find(self, run: SyncRun, stage_id: str) -> dict[str, Any]:
        for stage in run.progress.get("stages") or []:
            if stage.get("id") == stage_id:
                return stage
        raise KeyError(stage_id)

    def begin(self, stage_id: str, detail: str = "") -> None:
        run = self._load()
        stage = self._find(run, stage_id)
        stage["status"] = "running"
        stage["started_at"] = _now_iso()
        stage["finished_at"] = None
        if detail:
            stage["detail"] = detail
        run.progress["current_stage_id"] = stage_id
        run.progress = deepcopy(run.progress)
        self._save(run)
        fl = get_sync_debug_log()
        if fl is not None:
            fl.stage_begin(stage_id, detail)

    def detail(self, stage_id: str, detail: str) -> None:
        run = self._load()
        stage = self._find(run, stage_id)
        stage["detail"] = detail
        run.progress = deepcopy(run.progress)
        self._save(run)
        fl = get_sync_debug_log()
        if fl is not None:
            fl.stage_progress(stage_id, detail=detail)

    def progress(
        self,
        stage_id: str,
        *,
        detail: str | None = None,
        substage: str | None = None,
        current: int | None = None,
        total: int | None = None,
        unit: str = "",
    ) -> None:
        run = self._load()
        stage = self._find(run, stage_id)
        if detail is not None:
            stage["detail"] = detail
        if substage is not None:
            stage["substage"] = substage
        prog = dict(stage.get("progress") or {})
        if current is not None:
            prog["current"] = current
        if total is not None:
            prog["total"] = total
        if unit:
            prog["unit"] = unit
        stage["progress"] = prog
        run.progress = deepcopy(run.progress)
        self._save(run)
        fl = get_sync_debug_log()
        if fl is not None:
            fl.stage_progress(
                stage_id,
                detail=detail,
                substage=substage,
                current=current,
                total=total,
                unit=unit,
            )

    def end(self, stage_id: str, detail: str = "", *, status: str = "done") -> None:
        run = self._load()
        stage = self._find(run, stage_id)
        stage["status"] = status
        stage["finished_at"] = _now_iso()
        if detail:
            stage["detail"] = detail
        run.progress = deepcopy(run.progress)
        self._save(run)
        fl = get_sync_debug_log()
        if fl is not None:
            fl.stage_end(stage_id, detail, status=status)

    def skip(self, stage_id: str, reason: str = "") -> None:
        self.end(stage_id, detail=reason, status="skipped")

    def fail(self, stage_id: str, detail: str) -> None:
        self.end(stage_id, detail=detail, status="failed")
