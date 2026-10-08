"""Job progress routes. Read-only -- the frontend polls these."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_active_user
from app.jobs import active_jobs, get_job
from app.models.user import User

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/active")
def list_active_jobs(
    kind: str | None = Query(None, description="Filter by kind, e.g. matching"),
    current_user: User = Depends(get_current_active_user),
):
    """Currently running jobs. Empty list means nothing is in progress."""
    jobs = active_jobs(kind)
    return {"count": len(jobs), "jobs": jobs}


@router.get("/{job_id}")
def job_detail(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job
