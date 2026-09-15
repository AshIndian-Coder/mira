"""Human review workflow - the CORE of MIRA.

    POST /api/v1/review/approve/{match_id}   Approve an AI suggestion
    POST /api/v1/review/reject/{match_id}    Reject an AI suggestion
    GET  /api/v1/review/queue                Pending items for the reviewer
    POST /api/v1/review/bulk-approve         Bulk approve

Approving a match:
    1. suggestion.status -> approved
    2. feedback row stored (active-learning signal)
    3. mappings created: if one side already has an active mapping, the
       other joins that CNMC; otherwise a new CNMC is generated from the
       pair (standardized description + UNSPSC/NIC taxonomy)
    4. audit log entry
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db.postgres import get_db
from app.models.cnmc import CNMC
from app.models.mapping import Mapping
from app.models.match_suggestion import MatchSuggestion
from app.models.material import Material
from app.models.user import User
from app.schemas.match_schema import (
    BulkReviewRequest,
    BulkReviewResponse,
    ReviewRequest,
    ReviewResponse,
    SuggestionListResponse,
    SuggestionListItem,
)
from app.services.active_learning.feedback_collector import store_feedback
from app.services.audit.audit_service import log_action
from app.services.cnmc_generator.code_generator import (
    create_cnmc_for_cluster,
)
from app.utils.constants import (
    AUDIT_APPROVE_MATCH,
    AUDIT_REJECT_MATCH,
    FEEDBACK_APPROVE,
    FEEDBACK_REJECT,
    MAPPING_STATUS_ACTIVE,
    MAPPING_TYPE_AI_SUGGESTED,
    SUGGESTION_STATUS_APPROVED,
    SUGGESTION_STATUS_PENDING,
    SUGGESTION_STATUS_REJECTED,
)
from app.utils.helpers import utcnow

router = APIRouter(prefix="/review", tags=["review"])


def _material_dict(material: Material) -> dict:
    return {
        "id": int(material.id),
        "cpse_id": material.cpse_id,
        "material_code": material.material_code,
        "description": material.description,
        "cleaned_description": material.cleaned_description,
        "attributes": dict(material.attributes or {}),
        "category": material.category,
    }


def _ensure_pending(db: Session, match_id: int) -> MatchSuggestion:
    suggestion = db.query(MatchSuggestion).filter(MatchSuggestion.id == match_id).first()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Match suggestion not found")
    if suggestion.status != SUGGESTION_STATUS_PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Suggestion is already {suggestion.status}",
        )
    return suggestion


def _process_review(
    db: Session,
    match_id: int,
    action: str,
    reason: Optional[str],
    user: User,
) -> ReviewResponse:
    """Shared approve/reject logic (used by single + bulk endpoints)."""
    suggestion = _ensure_pending(db, match_id)
    material_1 = suggestion.material_1
    material_2 = suggestion.material_2
    is_approve = action == FEEDBACK_APPROVE

    # 1) current state
    suggestion.status = SUGGESTION_STATUS_APPROVED if is_approve else SUGGESTION_STATUS_REJECTED
    suggestion.reviewed_by = user.id
    suggestion.reviewed_at = utcnow()
    if reason:
        suggestion.review_comments = reason[:500]

    # 2) feedback (active learning signal)
    store_feedback(db, suggestion, user.id, action, reason)

    mapping_ids: List[int] = []
    cnmc_code: Optional[str] = None

    if is_approve:
        # 3) resolve / create the CNMC + mappings
        mapping_1 = (
            db.query(Mapping)
            .filter(Mapping.material_id == material_1.id, Mapping.status == MAPPING_STATUS_ACTIVE)
            .first()
        )
        mapping_2 = (
            db.query(Mapping)
            .filter(Mapping.material_id == material_2.id, Mapping.status == MAPPING_STATUS_ACTIVE)
            .first()
        )
        confidence = float(suggestion.final_confidence or 0)

        if mapping_1 and mapping_2 and mapping_1.cnmc_id == mapping_2.cnmc_id:
            # Already mapped to the same CNMC - nothing to do.
            cnmc_code = mapping_1.cnmc.cnmc_code
            mapping_ids = [mapping_1.id, mapping_2.id]
        elif mapping_1 and mapping_2:
            # Both mapped but to DIFFERENT CNMCs: merge into the larger
            # cluster and supersede the smaller one's mapping.
            size_1 = len(mapping_1.cnmc.mappings or [])
            size_2 = len(mapping_2.cnmc.mappings or [])
            target = mapping_1 if size_1 >= size_2 else mapping_2
            loser = mapping_2 if target is mapping_1 else mapping_1
            loser.status = "superseded"
            db.flush()
            db.add(
                Mapping(
                    material_id=int(loser.material_id),
                    cnmc_id=target.cnmc_id,
                    confidence_score=confidence,
                    mapping_type=MAPPING_TYPE_AI_SUGGESTED,
                    approved_by=user.id,
                    approved_at=utcnow(),
                    status=MAPPING_STATUS_ACTIVE,
                )
            )
            db.flush()
            cnmc_code = target.cnmc.cnmc_code
            mapping_ids = [m.id for m in target.cnmc.mappings]
        elif mapping_1 or mapping_2:
            target = mapping_1 or mapping_2
            incoming = material_2 if mapping_1 else material_1
            db.add(
                Mapping(
                    material_id=int(incoming.id),
                    cnmc_id=target.cnmc_id,
                    confidence_score=confidence,
                    mapping_type=MAPPING_TYPE_AI_SUGGESTED,
                    approved_by=user.id,
                    approved_at=utcnow(),
                    status=MAPPING_STATUS_ACTIVE,
                )
            )
            db.flush()
            cnmc_code = target.cnmc.cnmc_code
            mapping_ids = [m.id for m in target.cnmc.mappings]
        else:
            cnmc = create_cnmc_for_cluster(
                db,
                [_material_dict(material_1), _material_dict(material_2)],
                approved_by=user.id,
                mapping_type=MAPPING_TYPE_AI_SUGGESTED,
                commit=False,
            )
            cnmc_code = cnmc.cnmc_code
            mapping_ids = [m.id for m in cnmc.mappings]

    # 4) audit
    log_action(
        db,
        user,
        AUDIT_APPROVE_MATCH if is_approve else AUDIT_REJECT_MATCH,
        entity_type="match_suggestion",
        entity_id=suggestion.id,
        changes={
            "material_1_id": material_1.id,
            "material_2_id": material_2.id,
            "final_confidence": float(suggestion.final_confidence or 0),
            "reason": reason,
            "cnmc_code": cnmc_code,
        },
        commit=True,
    )
    db.commit()

    return ReviewResponse(
        match_id=suggestion.id,
        status=suggestion.status,
        cnmc_code=cnmc_code,
        mapping_ids=sorted(set(mapping_ids)),
        reason=reason,
        message=(
            f"Match approved and mapped to {cnmc_code}"
            if is_approve
            else "Match rejected (fed into active learning)"
        ),
    )


@router.post("/approve/{match_id}", response_model=ReviewResponse)
def approve_match(
    match_id: int,
    payload: ReviewRequest = ReviewRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review_match")),
):
    """Approve an AI match suggestion (creates mappings + CNMC if needed)."""
    return _process_review(db, match_id, FEEDBACK_APPROVE, payload.reason, user)


@router.post("/reject/{match_id}", response_model=ReviewResponse)
def reject_match(
    match_id: int,
    payload: ReviewRequest = ReviewRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review_match")),
):
    """Reject an AI match suggestion (negative training signal)."""
    return _process_review(db, match_id, FEEDBACK_REJECT, payload.reason, user)


@router.get("/queue", response_model=SuggestionListResponse)
def review_queue(
    decision: Optional[str] = Query(default=None, pattern="^(HIGH_CONFIDENCE|REVIEW|DIFFERENT)$"),
    min_confidence: Optional[float] = Query(default=None, ge=0, le=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Pending review queue, highest confidence first."""
    from app.api.v1.routes_matching import _filter_by_decision

    query = db.query(MatchSuggestion).filter(MatchSuggestion.status == SUGGESTION_STATUS_PENDING)
    if decision:
        query = _filter_by_decision(db, query, decision)
    if min_confidence is not None:
        query = query.filter(MatchSuggestion.final_confidence >= min_confidence)

    total = query.count()
    items = (
        query.order_by(desc(MatchSuggestion.final_confidence), desc(MatchSuggestion.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    counts = {"HIGH_CONFIDENCE": 0, "REVIEW": 0, "DIFFERENT": 0}
    for suggestion in items:
        d = (suggestion.explanation or {}).get("decision", "REVIEW")
        counts[d] = counts.get(d, 0) + 1
    return SuggestionListResponse(
        items=[SuggestionListItem.from_orm_object(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
        counts=counts,
    )


@router.post("/bulk-approve", response_model=BulkReviewResponse)
def bulk_approve(
    payload: BulkReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review_match")),
):
    """Approve multiple suggestions in one call."""
    approved, rejected, errors = 0, 0, []
    for match_id in payload.match_ids:
        try:
            _process_review(db, match_id, FEEDBACK_APPROVE, payload.reason, user)
            approved += 1
        except HTTPException as exc:
            errors.append({"match_id": match_id, "error": exc.detail})
            rejected += 1
        except Exception as exc:  # keep the bulk going
            errors.append({"match_id": match_id, "error": str(exc)})
            rejected += 1
    return BulkReviewResponse(approved=approved, rejected=0, failed=rejected, errors=errors)

