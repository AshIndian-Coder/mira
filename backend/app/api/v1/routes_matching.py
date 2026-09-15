"""AI matching endpoints.

    POST /api/v1/matching/run              Trigger AI matching (background-free)
    GET  /api/v1/matching/suggestions      Pending match suggestions (queue)
    GET  /api/v1/matching/suggestions/{id} Full suggestion + explanation
    POST /api/v1/matching/bulk-match       Alias of /run for explicit material lists
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rbac import require_permission
from app.core.security import get_current_active_user
from app.db.postgres import get_db
from app.models.material import Material
from app.models.match_suggestion import MatchSuggestion
from app.models.user import User
from app.schemas.match_schema import (
    MatchRunRequest,
    MatchRunResult,
    MatchSuggestionResponse,
    SuggestionListResponse,
    SuggestionListItem,
)
from app.services.audit.audit_service import log_action
from app.services.matching_engine import MatchingEngine
from app.utils.constants import AUDIT_RUN_MATCHING, SUGGESTION_STATUS_PENDING

router = APIRouter(prefix="/matching", tags=["matching"])


def _material_to_dict(material: Material) -> dict:
    return {
        "id": int(material.id),
        "cpse_id": material.cpse_id,
        "material_code": material.material_code,
        "description": material.description,
        "cleaned_description": material.cleaned_description,
        "attributes": dict(material.attributes or {}),
        "category": material.category,
        "uom_normalized": material.uom_normalized,
    }


def _filter_by_decision(db: Session, query, decision: str):
    """Filter suggestions by their stored decision label (explanation JSONB).

    Production-ready for both PostgreSQL (JSONB) and SQLite (dev fallback).

    Postgres:  Casts to JSONB and uses @> containment (GIN-indexable, works
               for both JSON and JSONB columns). Falls back to text cast
               if JSONB unavailable. Handles NULL explanations safely.
    SQLite:    Uses json_extract (SQLite json1 extension).
    Other DBs: No filtering (safe no-op).
    """
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        try:
            from sqlalchemy.dialects.postgresql import JSONB

            # Primary production path: JSONB containment - fast + indexable.
            # Works whether column is JSON or JSONB (we cast to JSONB).
            # Uses bound parameter so SQLAlchemy renders correct ::jsonb cast.
            return query.filter(
                MatchSuggestion.explanation.cast(JSONB).contains({"decision": decision})
            )
        except Exception:
            # Ultra-fallback: cast to TEXT and LIKE (never fails, but slower).
            # This path protects against exotic Postgres configs where JSONB
            # extension is unavailable.
            from sqlalchemy import Text

            return query.filter(
                MatchSuggestion.explanation.cast(Text).like(f'%"decision": "{decision}"%')
            )
    if dialect == "sqlite":
        from sqlalchemy import func as sa_func

        # NULL-safe: json_extract returns NULL for missing key, which != decision
        return query.filter(
            sa_func.json_extract(MatchSuggestion.explanation, "$.decision") == decision
        )
    return query  # other dialects: no decision filtering


def _resolve_source_materials(
    db: Session, request: MatchRunRequest
) -> list:
    """Pick the materials that will drive this matching run."""
    query = db.query(Material).filter(Material.status == "active")
    if request.material_ids:
        query = query.filter(Material.id.in_(request.material_ids))
    elif request.upload_batch_id:
        query = query.filter(Material.upload_batch_id == request.upload_batch_id)
    if request.cpse_id:
        query = query.filter(Material.cpse_id == request.cpse_id)
    return query.order_by(Material.id.asc()).limit(request.limit).all()


def _ensure_all_indexed(db: Session, engine: MatchingEngine) -> int:
    """Index every active material that the vector store may not know yet."""
    materials = db.query(Material).filter(Material.status == "active").all()
    if not materials:
        return 0
    return engine.vectors.index_materials([_material_to_dict(m) for m in materials])


def _existing_suggestion_ids(db: Session, material_ids) -> set:
    """Suggestion rows already present for any of these materials."""
    if not material_ids:
        return set()
    rows = (
        db.query(MatchSuggestion.material_1_id, MatchSuggestion.material_2_id)
        .filter(
            (MatchSuggestion.material_1_id.in_(material_ids))
            | (MatchSuggestion.material_2_id.in_(material_ids))
        )
        .all()
    )
    return {
        (min(a, b), max(a, b))
        for a, b in rows
    }


def _run_matching(db: Session, request: MatchRunRequest, user: User) -> MatchRunResult:
    engine = MatchingEngine()
    sources = _resolve_source_materials(db, request)
    if not sources:
        raise HTTPException(
            status_code=400, detail="No materials match the requested scope"
        )

    # Make sure the whole corpus is indexed (fresh in-memory stores need it).
    _ensure_all_indexed(db, engine)

    # Candidate pool: everything except sources of the same CPSE by default.
    all_materials = {
        int(m.id): _material_to_dict(m)
        for m in db.query(Material).filter(Material.status == "active").all()
    }
    for source in sources:
        d = _material_to_dict(source)
        all_materials.setdefault(int(d["id"]), d)

    existing_pairs = _existing_suggestion_ids(db, set(all_materials.keys()))
    candidates_evaluated = 0
    suggestions_created = 0
    suggestions_existing = 0
    by_decision = {"HIGH_CONFIDENCE": 0, "REVIEW": 0, "DIFFERENT": 0}

    for source in sources:
        source_dict = _material_to_dict(source)
        exclude_cpse = (
            None if request.include_same_cpse else source_dict["cpse_id"]
        )
        results = engine.match_material(
            source_dict,
            top_k=settings.VECTOR_TOP_K,
            exclude_cpse_id=exclude_cpse,
            min_confidence=request.min_confidence,
        )
        candidates_evaluated += len(results)
        for result in results:
            pair_key = (
                min(result["material_1_id"], result["material_2_id"]),
                max(result["material_1_id"], result["material_2_id"]),
            )
            if pair_key in existing_pairs:
                suggestions_existing += 1
                continue
            existing_pairs.add(pair_key)
            suggestion = MatchSuggestion(
                material_1_id=pair_key[0],
                material_2_id=pair_key[1],
                semantic_similarity=round(result["semantic_similarity"] * 100, 2),
                fuzzy_similarity=round(result["fuzzy_similarity"] * 100, 2),
                attribute_similarity=round(result["attribute_similarity"] * 100, 2),
                final_confidence=round(result["final_confidence"] * 100, 2),
                explanation=result["explanation"],
                status=SUGGESTION_STATUS_PENDING,
            )
            db.add(suggestion)
            suggestions_created += 1
            by_decision[result["decision"]] = by_decision.get(result["decision"], 0) + 1

    db.commit()
    log_action(
        db,
        user,
        AUDIT_RUN_MATCHING,
        entity_type="matching_run",
        changes={
            "processed": len(sources),
            "suggestions_created": suggestions_created,
            "by_decision": by_decision,
        },
        commit=True,
    )
    return MatchRunResult(
        processed=len(sources),
        candidates_evaluated=candidates_evaluated,
        suggestions_created=suggestions_created,
        suggestions_existing=suggestions_existing,
        by_decision=by_decision,
        embedding_backend=engine.embeddings.backend,
        vector_backend=engine.vectors.backend_name,
    )


@router.post("/run", response_model=MatchRunResult)
def run_matching(
    request: MatchRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("run_matching")),
):
    """Run hybrid AI matching over a scope of materials."""
    return _run_matching(db, request, user)


@router.post("/bulk-match", response_model=MatchRunResult)
def bulk_match(
    request: MatchRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("run_matching")),
):
    """Batch matching for an explicit list of material ids."""
    if not request.material_ids:
        raise HTTPException(status_code=400, detail="material_ids is required for bulk-match")
    return _run_matching(db, request, user)


@router.get("/suggestions", response_model=SuggestionListResponse)
def list_suggestions(
    status: Optional[str] = Query(default="pending", pattern="^(pending|approved|rejected)$"),
    decision: Optional[str] = Query(default=None, pattern="^(HIGH_CONFIDENCE|REVIEW|DIFFERENT)$"),
    cpse_id: Optional[int] = Query(default=None),
    min_confidence: Optional[float] = Query(default=None, ge=0, le=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Match review queue (MatchReviewQueue page)."""
    query = db.query(MatchSuggestion).filter(MatchSuggestion.status == status)
    if min_confidence is not None:
        query = query.filter(MatchSuggestion.final_confidence >= min_confidence)
    if decision:
        # decision is stored inside explanation JSONB
        query = _filter_by_decision(db, query, decision)
    if cpse_id:
        query = query.filter(
            (MatchSuggestion.material_1_id.in_(
                db.query(Material.id).filter(Material.cpse_id == cpse_id)
            ))
            | (MatchSuggestion.material_2_id.in_(
                db.query(Material.id).filter(Material.cpse_id == cpse_id)
            ))
        )

    total = query.count()
    items = (
        query.order_by(desc(MatchSuggestion.final_confidence), desc(MatchSuggestion.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Queue counts by decision (for the filter chips)
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


@router.get("/suggestions/{match_id}", response_model=MatchSuggestionResponse)
def suggestion_detail(
    match_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Full suggestion detail including the Explainable AI payload."""
    suggestion = db.query(MatchSuggestion).filter(MatchSuggestion.id == match_id).first()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Match suggestion not found")
    return MatchSuggestionResponse.from_orm_object(suggestion)

