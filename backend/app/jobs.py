"""
In-process job progress registry.

A single uvicorn worker keeps this in memory, which is enough: the frontend
polls GET /api/jobs/active while the long-running request is still in flight,
and can therefore recover the true state after a page navigation or reload.
Nothing here is persisted -- a restart means no job is running, which is true.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_MAX_KEPT = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(kind: str, *, total: int = 0, detail: str = "") -> str:
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "kind": kind,
            "phase": "starting",
            "processed": 0,
            "total": total,
            "status": "running",
            "detail": detail,
            "started_at": _now(),
            "finished_at": None,
            "error": None,
            "result": None,
        }
        # Trim finished jobs so the dict cannot grow without bound.
        finished = [k for k, v in _JOBS.items() if v["status"] != "running"]
        for k in finished[:-_MAX_KEPT]:
            _JOBS.pop(k, None)
    return job_id


def update_job(
    job_id: str,
    *,
    phase: str | None = None,
    processed: int | None = None,
    total: int | None = None,
    detail: str | None = None,
) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        if phase is not None:
            job["phase"] = phase
        if processed is not None:
            job["processed"] = processed
        if total is not None:
            job["total"] = total
        if detail is not None:
            job["detail"] = detail


def finish_job(job_id: str, *, result: Any = None, error: str | None = None) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job["status"] = "failed" if error else "completed"
        job["finished_at"] = _now()
        job["result"] = result
        job["error"] = error


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def active_jobs(kind: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        jobs = [dict(j) for j in _JOBS.values() if j["status"] == "running"]
    if kind is not None:
        jobs = [j for j in jobs if j["kind"] == kind]
    jobs.sort(key=lambda j: j["started_at"])
    return jobs
