"""
Human review queue routes.

GET  /api/review/queue              — pending REVIEW-decision candidates
GET  /api/review/queue/{id}         — single review item detail
POST /api/review/queue/{id}/action  — APPROVE or REJECT a candidate
GET  /api/review/summary            — counts: pending / approved / rejected
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import store
from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/review", tags=["Review Queue"])


class ReviewActionRequest(BaseModel):
    action: str                         # "APPROVE" or "REJECT"
    reviewer_comments: str | None = None
    user_id: str | None = None          # Deprecated/optional client identifier


@router.get("/queue")
def get_review_queue(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
):
    """
    Return candidates that the engine flagged as REVIEW and are still PENDING.
    These are the items that need human judgement.
    """
    pending = [
        c for c in store.CANDIDATES
        if c["engine_decision"] in {"HIGH_CONFIDENCE", "REVIEW"}
        and c["review_status"] == "PENDING"
    ]
    total = len(pending)
    paginated = pending[skip: skip + limit]

    return {
        "total_pending": total,
        "skip": skip,
        "limit": limit,
        "queue": paginated,
    }


@router.get("/queue/{candidate_id}")
def get_review_item(
    candidate_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve a single review item with full score breakdown and critical checks."""
    for c in store.CANDIDATES:
        if c["id"] == candidate_id:
            return c
    raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")


@router.post("/queue/{candidate_id}/action")
def submit_review_action(
    candidate_id: int,
    request: ReviewActionRequest,
    current_user: User = Depends(require_permission("review_match")),
):
    """
    Human reviewer approves or rejects a candidate pair.

    - Sets review_status to APPROVED or REJECTED.
    - Records reviewer identity from authenticated user and timestamp.
    - Appends an audit event with real actor.
    - Returns the updated candidate.
    """
    action = request.action.upper()
    if action not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="action must be APPROVE or REJECT")

    candidate = None
    for c in store.CANDIDATES:
        if c["id"] == candidate_id:
            candidate = c
            break

    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")

    if candidate["review_status"] not in ("PENDING", "REVIEW"):
        raise HTTPException(
            status_code=409,
            detail=f"Candidate already has status '{candidate['review_status']}'",
        )

    actor_identity = current_user.email if (current_user and current_user.email) else (request.user_id or "reviewer")
    now = datetime.now(timezone.utc).isoformat()
    candidate["review_status"] = "APPROVED" if action == "APPROVE" else "REJECTED"
    candidate["reviewer_id"] = actor_identity
    candidate["reviewer_comments"] = request.reviewer_comments
    candidate["reviewed_at"] = now

    # Emit audit event (consumed by /api/audit route)
    from app.api.v1.audit import AUDIT_EVENTS  # local import to avoid circular dep
    event_type = "MATCH_APPROVED" if action == "APPROVE" else "MATCH_REJECTED"
    AUDIT_EVENTS.append({
        "event_type": event_type,
        "candidate_id": candidate_id,
        "source_code": candidate["source_code"],
        "target_code": candidate["target_code"],
        "source_cpse": candidate["source_cpse"],
        "target_cpse": candidate["target_cpse"],
        "actor": actor_identity,
        "comments": request.reviewer_comments,
        "final_score": candidate["scores"].get("final_score"),
        "timestamp": now,
    })

    return {
        "status": "success",
        "candidate_id": candidate_id,
        "action_applied": action,
        "candidate": candidate,
    }


@router.get("/summary")
def review_summary(current_user: User = Depends(get_current_active_user)):
    """Counts of review-queue items by status — for the dashboard card."""
    review_candidates = [c for c in store.CANDIDATES if c["engine_decision"] == "REVIEW"]
    pending = sum(1 for c in review_candidates if c["review_status"] == "PENDING")
    approved = sum(1 for c in review_candidates if c["review_status"] == "APPROVED")
    rejected = sum(1 for c in review_candidates if c["review_status"] == "REJECTED")

    # HIGH_CONFIDENCE recommendations are still subject to human validation.
    high_confidence = sum(
        1 for c in store.CANDIDATES
        if c["engine_decision"] == "HIGH_CONFIDENCE"
    )

    return {
        "total_review_queue": len(review_candidates),
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "high_confidence": high_confidence,
    }
