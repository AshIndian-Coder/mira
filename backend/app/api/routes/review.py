"""
Human review queue routes.

GET  /api/review/queue              — pending REVIEW-decision candidates
GET  /api/review/queue/{id}         — single review item detail
POST /api/review/queue/{id}/action  — APPROVE or REJECT a candidate
GET  /api/review/summary            — counts: pending / approved / rejected
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store

router = APIRouter(prefix="/review", tags=["Review Queue"])


class ReviewActionRequest(BaseModel):
    action: str                         # "APPROVE" or "REJECT"
    reviewer_comments: str | None = None
    user_id: str = "operator_01"


@router.get("/queue")
def get_review_queue(skip: int = 0, limit: int = 50):
    """
    Return candidates that the engine flagged as REVIEW and are still PENDING.
    These are the items that need human judgement.
    """
    pending = [
        c for c in store.CANDIDATES
        if c["engine_decision"] == "REVIEW" and c["review_status"] == "PENDING"
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
def get_review_item(candidate_id: int):
    """Retrieve a single review item with full score breakdown and critical checks."""
    for c in store.CANDIDATES:
        if c["id"] == candidate_id:
            return c
    raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")


@router.post("/queue/{candidate_id}/action")
def submit_review_action(candidate_id: int, request: ReviewActionRequest):
    """
    Human reviewer approves or rejects a candidate pair.

    - Sets review_status to APPROVED or REJECTED.
    - Records reviewer identity and timestamp.
    - Appends an audit event.
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

    now = datetime.now(timezone.utc).isoformat()
    candidate["review_status"] = "APPROVED" if action == "APPROVE" else "REJECTED"
    candidate["reviewer_id"] = request.user_id
    candidate["reviewer_comments"] = request.reviewer_comments
    candidate["reviewed_at"] = now

    # Emit audit event (consumed by /api/audit route)
    from app.api.routes.audit import AUDIT_EVENTS  # local import to avoid circular dep
    AUDIT_EVENTS.append({
        "event_type": f"MATCH_{action}D",
        "candidate_id": candidate_id,
        "source_code": candidate["source_code"],
        "target_code": candidate["target_code"],
        "source_cpse": candidate["source_cpse"],
        "target_cpse": candidate["target_cpse"],
        "actor": request.user_id,
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
def review_summary():
    """Counts of review-queue items by status — for the dashboard card."""
    review_candidates = [c for c in store.CANDIDATES if c["engine_decision"] == "REVIEW"]
    pending = sum(1 for c in review_candidates if c["review_status"] == "PENDING")
    approved = sum(1 for c in review_candidates if c["review_status"] == "APPROVED")
    rejected = sum(1 for c in review_candidates if c["review_status"] == "REJECTED")

    # HIGH_CONFIDENCE that were auto-accepted (no human needed)
    auto_accepted = sum(
        1 for c in store.CANDIDATES if c["engine_decision"] == "HIGH_CONFIDENCE"
    )

    return {
        "total_review_queue": len(review_candidates),
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "auto_accepted_high_confidence": auto_accepted,
    }
