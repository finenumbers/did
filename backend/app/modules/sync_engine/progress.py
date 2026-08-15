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

# Run is still allowed to mutate progress while in these statuses.
_ACTIVE_RUN_STATUSES = frozenset({"pending", "running"})


class SyncAborted(Exception):
    """Run was cancelled externally (orphan reclaim / restart) — stop the worker."""


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
    {"id": "exolve_dictionaries", "group": "Exolve", "label": "Справочники"},
    {"id": "exolve_free", "group": "Exolve", "label": "Свободные номера"},
    {"id": "voximplant_dictionaries", "group": "Voximplant", "label": "Справочники"},
    {"id": "voximplant_free", "group": "Voximplant", "label": "Свободные номера"},
    {"id": "mcn_dictionaries", "group": "MCN Telecom", "label": "Справочники"},
    {"id": "mcn_free", "group": "MCN Telecom", "label": "Свободные номера"},
    {"id": "finenumbers_free", "group": "Finenumbers", "label": "Свободные номера"},
    {"id": "operator_enrichment", "group": "Общее", "label": "Обогащение PSTN"},
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
    ("exolve", "dictionaries"): "exolve_dictionaries",
    ("exolve", "free"): "exolve_free",
    ("voximplant", "dictionaries"): "voximplant_dictionaries",
    ("voximplant", "free"): "voximplant_free",
    ("mcn", "dictionaries"): "mcn_dictionaries",
    ("mcn", "free"): "mcn_free",
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


def finalize_progress_on_abort(
    progress: dict[str, Any] | None,
    reason: str,
) -> dict[str, Any] | None:
    """Close open stages when a run is aborted (orphan / stale / restart).

    ``running`` → ``failed``; ``pending`` → ``skipped``. Finished stages unchanged.
    """
    if not progress or not isinstance(progress, dict):
        return progress
    stages = progress.get("stages")
    if not isinstance(stages, list):
        return progress
    now = _now_iso()
    detail = f"aborted: {reason}"
    changed = False
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        status = stage.get("status")
        if status == "running":
            stage["status"] = "failed"
            stage["finished_at"] = now
            prev = (stage.get("detail") or "").strip()
            stage["detail"] = f"{prev} · {detail}" if prev else detail
            stage["substage"] = ""
            changed = True
        elif status == "pending":
            stage["status"] = "skipped"
            stage["finished_at"] = now
            stage["detail"] = detail
            changed = True
    if changed:
        progress = deepcopy(progress)
        progress["current_stage_id"] = None
    return progress


def apply_progress_abort(run: SyncRun, reason: str) -> None:
    """Mutate ``run.progress`` open stages and mark the column dirty for ORM."""
    from sqlalchemy.orm.attributes import flag_modified

    updated = finalize_progress_on_abort(getattr(run, "progress", None), reason)
    if updated is None:
        return
    run.progress = updated
    try:
        flag_modified(run, "progress")
    except (AttributeError, TypeError):
        # Plain namespace / unmapped object in unit tests.
        pass


def build_stage_timings(progress: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Per-stage wall times from progress started_at/finished_at (ISO UTC)."""
    if not progress:
        return []
    out: list[dict[str, Any]] = []
    for stage in progress.get("stages") or []:
        started = stage.get("started_at")
        finished = stage.get("finished_at")
        duration_s: float | None = None
        if started and finished:
            try:
                t0 = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
                duration_s = round((t1 - t0).total_seconds(), 3)
            except (TypeError, ValueError):
                duration_s = None
        out.append(
            {
                "id": stage.get("id"),
                "status": stage.get("status"),
                "started_at": started,
                "finished_at": finished,
                "duration_s": duration_s,
                "detail": stage.get("detail") or "",
            }
        )
    return out


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

    def _ensure_active(self, run: SyncRun) -> None:
        """Refuse progress writes after reclaim/interrupt marked the run failed."""
        self.db.refresh(run)
        raw = getattr(run, "status", None)
        if raw is None:
            return
        status = raw.value if hasattr(raw, "value") else str(raw)
        if status not in _ACTIVE_RUN_STATUSES:
            raise SyncAborted(
                f"Sync run stopped externally (status={status})"
            )

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
        self._ensure_active(run)
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
        self._ensure_active(run)
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
        self._ensure_active(run)
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
        self._ensure_active(run)
        stage = self._find(run, stage_id)
        stage["status"] = status
        stage["finished_at"] = _now_iso()
        if detail:
            stage["detail"] = detail
        # Finished stages keep a single final detail — drop in-flight counters so the
        # UI does not append a stale "current / total" next to the summary.
        stage["substage"] = ""
        stage["progress"] = {"current": None, "total": None, "unit": ""}
        run.progress = deepcopy(run.progress)
        self._save(run)
        fl = get_sync_debug_log()
        if fl is not None:
            fl.stage_end(stage_id, detail, status=status)

    def skip(self, stage_id: str, reason: str = "") -> None:
        self.end(stage_id, detail=reason, status="skipped")

    def fail(self, stage_id: str, detail: str) -> None:
        self.end(stage_id, detail=detail, status="failed")
